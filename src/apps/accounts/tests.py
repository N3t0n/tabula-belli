from datetime import timedelta
from unittest.mock import patch
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from allauth.account.models import EmailAddress
from cities_light.models import City, Country
from django.contrib.auth import SESSION_KEY
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.deletion import AccountDeletionBlocked, confirmation_token, delete_account, deletion_review
from apps.events.admin import EventRegistrationAdmin
from apps.events.models import Event, EventRegistration
from apps.games.models import Game
from apps.players.models import Player


class AccountDeletionTest(TestCase):
    def setUp(self):
        country = Country.objects.create(name='Account Country', code2='AC', code3='ACT')
        self.city = City.objects.create(name='Account City', slug='account-city', country=country)
        self.game = Game.objects.create(name='Account Game', slug='account-game', category=Game.Category.TCG)
        self.user = Player.objects.create_user(username='account-user', email='user@account.test')
        self.other = Player.objects.create_user(username='other-player', email='other@account.test')
        EmailAddress.objects.create(user=self.user, email=self.user.email, primary=True, verified=True)
        self.url = reverse('accounts:profile')
        self.delete_url = reverse('accounts:delete')
        self.client.force_login(self.user)

    def event(self, slug, owner=None, **kwargs):
        now = timezone.now()
        fields = dict(title=slug, slug=slug, organizer=owner or self.user,
                      country=self.city.country, city=self.city, game=self.game,
                      contact_email='contact@account.test', start_at=now+timedelta(days=2),
                      end_at=now+timedelta(days=2, hours=2), capacity=5)
        fields.update(kwargs)
        return Event.objects.create(**fields)

    def confirmed_delete(self, **kwargs):
        response = self.client.get(self.delete_url)
        return self.client.post(self.delete_url, {'confirmation': response.context['confirmation']}, **kwargs)

    def test_future_events_and_registrations_cancel_without_deleting_history(self):
        owned = self.event('owned')
        elsewhere = self.event('other', owner=self.other)
        participant = EventRegistration.objects.create(event=owned, player=self.other)
        mine = EventRegistration.objects.create(event=elsewhere, player=self.user)
        review = self.client.get(self.delete_url)
        self.assertContains(review, 'Cancel pending items and delete my account')
        self.assertEqual(len(review.context['review'].future_events), 1)
        self.assertEqual(len(review.context['review'].pending_registrations), 1)
        response = self.confirmed_delete()
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        for record in [owned, elsewhere, participant, mine]:
            record.refresh_from_db()
        self.assertEqual(owned.status, Event.Status.CANCELED)
        self.assertIsNone(owned.organizer_id)
        self.assertEqual(owned.contact_email, '')
        self.assertEqual(participant.status, EventRegistration.Status.CANCELLED)
        self.assertEqual(participant.player_id, self.other.pk)
        self.assertIsNotNone(participant.cancelled_at)
        self.assertEqual(mine.status, EventRegistration.Status.CANCELLED)
        self.assertIsNone(mine.player_id)
        self.assertIsNotNone(mine.cancelled_at)
        self.assertEqual(elsewhere.status, Event.Status.ACTIVE)
        self.assertEqual(elsewhere.organizer_id, self.other.pk)
        self.assertEqual(elsewhere.contact_email, 'contact@account.test')
        self.assertEqual(elsewhere.registrations.filter(status='CONFIRMED').count(), 0)
        self.assertFalse(Player.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(EmailAddress.objects.filter(email=self.user.email).exists())
        self.assertNotIn(SESSION_KEY, self.client.session)
        owned.full_clean()

    def test_past_history_counts_and_deleted_account_display(self):
        now = timezone.now()
        past = dict(start_at=now-timedelta(days=2), end_at=now-timedelta(days=1), status=Event.Status.COMPLETED)
        owned = self.event('past-owned', **past)
        elsewhere = self.event('past-other', owner=self.other, **past)
        participant = EventRegistration.objects.create(event=owned, player=self.other)
        mine = EventRegistration.objects.create(event=elsewhere, player=self.user)
        self.confirmed_delete()
        for record in [owned, mine, participant]:
            record.refresh_from_db()
        self.assertEqual(owned.status, Event.Status.COMPLETED)
        self.assertEqual(owned.organizer_display, 'Deleted account')
        self.assertEqual(owned.contact_email, '')
        self.assertEqual(mine.status, EventRegistration.Status.CONFIRMED)
        self.assertIsNone(mine.player_id)
        self.assertEqual(participant.player_id, self.other.pk)
        self.assertEqual(participant.status, EventRegistration.Status.CONFIRMED)
        self.assertEqual(elsewhere.registrations.filter(status='CONFIRMED').count(), 1)
        self.assertIn('Deleted account', str(mine))
        self.assertEqual(EventRegistrationAdmin.player_username(None, mine), 'Deleted account')
        self.client.force_login(self.other)
        response = self.client.get(reverse('event_detail', args=[elsewhere.slug]))
        self.assertContains(response, 'Deleted account')
        self.assertNotContains(response, self.user.email)
        self.assertNotContains(response, self.user.username)
        response = self.client.get(reverse('event_detail', args=[owned.slug]))
        self.assertContains(response, 'Deleted account')
        self.assertNotContains(response, 'mailto:contact@account.test')

    def test_canceled_events_do_not_block_deletion(self):
        event = self.event('canceled', status=Event.Status.CANCELED)
        self.confirmed_delete()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CANCELED)
        self.assertIsNone(event.organizer_id)
        self.assertFalse(Player.objects.filter(pk=self.user.pk).exists())

    def test_stale_active_event_ended_by_date_is_completed(self):
        now = timezone.now()
        event = self.event('ended', start_at=now-timedelta(days=2), end_at=now-timedelta(days=1))
        reg = EventRegistration.objects.create(event=event, player=self.other)
        self.confirmed_delete()
        event.refresh_from_db(); reg.refresh_from_db()
        self.assertEqual(event.status, Event.Status.COMPLETED)
        self.assertIsNone(event.organizer_id)
        self.assertEqual(reg.status, EventRegistration.Status.CONFIRMED)

    def test_in_progress_blocks_without_changing_account_or_future_events(self):
        now = timezone.now()
        current = self.event('current', start_at=now-timedelta(hours=1), end_at=now+timedelta(hours=1))
        future = self.event('future')
        review = self.client.get(self.delete_url)
        self.assertContains(review, 'while an event you organize is in progress')
        self.assertNotContains(review, 'name="confirmation"')
        response = self.client.post(self.delete_url, {'confirmation': review.context['confirmation']}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 409)
        future.refresh_from_db(); current.refresh_from_db()
        self.assertEqual(future.status, Event.Status.ACTIVE)
        self.assertEqual(current.organizer_id, self.user.pk)
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.user.pk)

    def test_new_events_or_registrations_require_a_new_review(self):
        token = self.client.get(self.delete_url).context['confirmation']
        owned = self.event('new-event')
        response = self.client.post(self.delete_url, {'confirmation': token}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 409)
        token = self.client.get(self.delete_url).context['confirmation']
        other = self.event('new-registration', owner=self.other)
        reg = EventRegistration.objects.create(event=other, player=self.user)
        response = self.client.post(self.delete_url, {'confirmation': token}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 409)
        owned.refresh_from_db(); reg.refresh_from_db()
        self.assertEqual(owned.status, Event.Status.ACTIVE)
        self.assertEqual(reg.status, EventRegistration.Status.CONFIRMED)

    def test_missing_tampered_expired_and_other_user_confirmations_are_rejected(self):
        token = confirmation_token(self.user, deletion_review(self.user))
        wrong_user = confirmation_token(self.other, deletion_review(self.other))
        for invalid in ['', token+'x', wrong_user]:
            response = self.client.post(self.delete_url, {'confirmation': invalid}, HTTP_HX_REQUEST='true')
            self.assertEqual(response.status_code, 409)
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp()-901):
            expired = confirmation_token(self.user, deletion_review(self.user))
        response = self.client.post(self.delete_url, {'confirmation': expired}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.user.pk)

    def test_failure_rolls_back_cancellation_anonymization_and_account_deletion(self):
        event = self.event('rollback')
        reg = EventRegistration.objects.create(event=event, player=self.other)
        mine = EventRegistration.objects.create(event=event, player=self.user)
        with patch.object(Player, 'delete', side_effect=ProtectedError('forced', set())):
            response = self.confirmed_delete(HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 409)
        event.refresh_from_db(); reg.refresh_from_db(); mine.refresh_from_db()
        self.assertEqual(event.status, Event.Status.ACTIVE)
        self.assertEqual(event.organizer_id, self.user.pk)
        self.assertEqual(event.contact_email, 'contact@account.test')
        self.assertEqual(reg.status, EventRegistration.Status.CONFIRMED)
        self.assertIsNone(reg.cancelled_at)
        self.assertEqual(mine.player_id, self.user.pk)
        self.assertTrue(EmailAddress.objects.filter(user=self.user).exists())
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.user.pk)

    def test_review_and_legacy_profile_submission_do_not_delete(self):
        event = self.event('review-only')
        self.client.get(self.delete_url)
        response = self.client.post(self.url, {'_method': 'DELETE'})
        self.assertRedirects(response, self.delete_url, fetch_redirect_response=False)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.ACTIVE)
        self.assertEqual(event.organizer_id, self.user.pk)
        self.assertTrue(Player.objects.filter(pk=self.user.pk).exists())

    def test_csrf_and_signed_review_then_email_and_username_can_be_reused(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        review = client.get(self.delete_url)
        token = review.context['confirmation']
        self.assertContains(review, 'name="csrfmiddlewaretoken"')
        self.assertEqual(client.post(self.delete_url, {'confirmation': token}).status_code, 403)
        added = Game.objects.create(name='Added', slug='added', category=Game.Category.TCG, created_by=self.user)
        response = client.post(self.delete_url, {
            'confirmation': token, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['HX-Redirect'], '/')
        added.refresh_from_db()
        self.assertIsNone(added.created_by_id)
        self.assertNotIn(SESSION_KEY, client.session)
        replacement = Player.objects.create_user(username=self.user.username, email=self.user.email)
        self.assertNotEqual(replacement.pk, self.user.pk)

    def test_demo_and_superuser_are_protected(self):
        users = [Player.objects.create_user(username='horus_lupercal', email='demo@account.test'),
                 Player.objects.create_superuser(username='admin', email='admin@account.test', password='test-only')]
        for user in users:
            self.client.force_login(user)
            self.assertNotContains(self.client.get(self.delete_url), 'name="confirmation"')
            token = confirmation_token(user, deletion_review(user))
            response = self.client.post(self.delete_url, {'confirmation': token}, HTTP_HX_REQUEST='true')
            self.assertEqual(response.status_code, 403)
            self.assertTrue(Player.objects.filter(pk=user.pk).exists())

    def test_anonymous_user_cannot_review_or_delete(self):
        self.client.logout()
        for method in [self.client.get, self.client.post]:
            response = method(self.delete_url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse('account_login'), response.url)

    def test_database_guards_against_accidental_delete_and_orphan_active_events(self):
        event = self.event('protected')
        with self.assertRaises(ProtectedError):
            self.user.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Event.objects.filter(pk=event.pk).update(organizer=None)
        event.refresh_from_db()
        self.assertEqual(event.organizer_id, self.user.pk)

    def test_future_event_starting_after_review_blocks_deletion(self):
        event = self.event('starting')
        token = self.client.get(self.delete_url).context['confirmation']
        with patch('apps.accounts.deletion.timezone.now', return_value=event.start_at+timedelta(minutes=1)):
            response = self.client.post(self.delete_url, {'confirmation': token}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Player.objects.filter(pk=self.user.pk).exists())

    def test_participation_in_others_ongoing_events_cancels_without_canceling_event(self):
        now = timezone.now()
        event = self.event('ongoing-other', owner=self.other, start_at=now-timedelta(hours=1), end_at=now+timedelta(hours=1))
        reg = EventRegistration.objects.create(event=event, player=self.user)
        self.confirmed_delete()
        reg.refresh_from_db(); event.refresh_from_db()
        self.assertEqual(reg.status, EventRegistration.Status.CANCELLED)
        self.assertIsNone(reg.player_id)
        self.assertEqual(event.status, Event.Status.ACTIVE)

    def test_repeated_deletion_is_safe_and_canceled_registration_date_is_retained(self):
        event = self.event('other-future', owner=self.other)
        canceled_at = timezone.now()-timedelta(days=1)
        reg = EventRegistration.objects.create(event=event, player=self.user, status=EventRegistration.Status.CANCELLED, cancelled_at=canceled_at)
        user_id = self.user.pk
        token = self.client.get(self.delete_url).context['confirmation']
        self.client.post(self.delete_url, {'confirmation': token})
        delete_account(user_id, token)
        reg.refresh_from_db()
        self.assertEqual(reg.status, EventRegistration.Status.CANCELLED)
        self.assertEqual(reg.cancelled_at, canceled_at)
        self.assertIsNone(reg.player_id)


    def test_normal_profile_update_redirects_and_invalid_form_is_full_page(self):
        self.client.force_login(self.user)

        invalid_response = self.client.post(self.url, {})
        self.assertEqual(invalid_response.status_code, 400)
        self.assertTemplateUsed(invalid_response, 'accounts/profile.html')
        self.assertContains(
            invalid_response, '<!DOCTYPE html>', status_code=400, html=False
        )
        self.assertContains(
            invalid_response, 'This field is required.', status_code=400
        )
        self.assertContains(
            invalid_response, f'action="{self.url}"', status_code=400
        )

        valid_response = self.client.post(self.url, {
            'username': self.user.username,
            'email': self.user.email,
            'first_name': 'Updated',
            'last_name': 'User',
            'country': '',
            'region': '',
            'city': '',
            'favorite_games': [],
        })
        self.assertRedirects(
            valid_response, self.url, fetch_redirect_response=False
        )


@skipUnless(connection.vendor == 'postgresql', 'Account deletion locking requires PostgreSQL')
class AccountDeletionConcurrencyTest(TransactionTestCase):
    setUp = AccountDeletionTest.setUp
    event = AccountDeletionTest.event

    def run_race(self, operations):
        barrier = Barrier(2)

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=15) for future in futures]

    def test_registration_racing_deletion_is_completed_or_requires_fresh_review(self):
        event = self.event('concurrent-registration', owner=self.other)
        user_id = self.user.pk
        token = confirmation_token(self.user, deletion_review(self.user))

        def delete():
            try:
                delete_account(user_id, token)
                return 'deleted'
            except AccountDeletionBlocked:
                return 'review-again'

        def register():
            try:
                EventRegistration.register(event=event, player=self.user)
                return 'registered'
            except ValidationError:
                return 'account-gone'

        outcomes = self.run_race([delete, register])
        if Player.objects.filter(pk=user_id).exists():
            self.assertEqual(outcomes, ['review-again', 'registered'])
            self.assertEqual(EventRegistration.objects.filter(player_id=user_id, status='CONFIRMED').count(), 1)
        else:
            self.assertEqual(outcomes, ['deleted', 'account-gone'])
            self.assertEqual(EventRegistration.objects.count(), 0)

    def test_two_confirmed_deletions_complete_once_without_losing_records(self):
        event = self.event('concurrent-delete')
        reg = EventRegistration.objects.create(event=event, player=self.other)
        user_id = self.user.pk
        token = confirmation_token(self.user, deletion_review(self.user))
        self.run_race([lambda: delete_account(user_id, token)] * 2)
        event.refresh_from_db(); reg.refresh_from_db()
        self.assertFalse(Player.objects.filter(pk=user_id).exists())
        self.assertEqual(event.status, Event.Status.CANCELED)
        self.assertIsNone(event.organizer_id)
        self.assertEqual(reg.status, EventRegistration.Status.CANCELLED)
        self.assertEqual(reg.player_id, self.other.pk)
