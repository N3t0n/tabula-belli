from datetime import timedelta
from io import StringIO

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from allauth.account.forms import default_token_generator
from allauth.account.utils import user_pk_to_url_str
from cities_light.models import City, Country, Region
from django.conf import settings
from django.contrib.auth import get_user
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.forms import ProfileForm
from apps.events.models import Event, EventRegistration
from apps.games.models import Game
from apps.players.models import Player


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class AuthDemoTest(TestCase):
    password = 'StrongTestPass123!'

    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(
            name='Auth Demo Country', code2='AD', code3='ADE'
        )
        cls.region = Region.objects.create(
            name='Auth Demo Region',
            slug='auth-demo-region',
            country=cls.country,
        )
        cls.city = City.objects.create(
            name='Auth Demo City',
            slug='auth-demo-city',
            country=cls.country,
            region=cls.region,
        )
        cls.game = Game.objects.create(
            name='Auth Demo Game',
            slug='auth-demo-game',
            category=Game.Category.TCG,
        )
        cls.demo = Player.objects.create_user(
            username=settings.PUBLIC_DEMO_USERNAME,
            email='public-demo@example.com',
            password=cls.password,
            first_name='Horus',
            last_name='Lupercal',
            country=cls.country,
            region=cls.region,
            city=cls.city,
        )
        EmailAddress.objects.create(
            user=cls.demo,
            email=cls.demo.email,
            primary=True,
            verified=True,
        )
        cls.normal = Player.objects.create_user(
            username='auth-demo-normal',
            email='normal@example.com',
            password=cls.password,
        )
        EmailAddress.objects.create(
            user=cls.normal,
            email=cls.normal.email,
            primary=True,
            verified=True,
        )

    def make_event(self, slug, organizer=None):
        now = timezone.now()
        return Event.objects.create(
            title=f'Auth Demo {slug}',
            slug=f'auth-demo-{slug}',
            organizer=organizer or self.normal,
            country=self.country,
            region=self.region,
            city=self.city,
            game=self.game,
            contact_email=f'{slug}@example.com',
            start_at=now + timedelta(days=3),
            end_at=now + timedelta(days=3, hours=2),
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=2),
            capacity=5,
        )

    def event_form_data(self, title):
        now = timezone.now()
        return {
            'event_type': Event.EventType.CASUAL,
            'title': title,
            'description': 'Demo event',
            'country': self.country.pk,
            'region': self.region.pk,
            'city': self.city.pk,
            'location_name': 'Demo venue',
            'location_address': 'Demo address',
            'start_at': (now + timedelta(days=4)).strftime('%Y-%m-%dT%H:%M'),
            'end_at': (now + timedelta(days=4, hours=2)).strftime('%Y-%m-%dT%H:%M'),
            'registration_opens_at': now.strftime('%Y-%m-%dT%H:%M'),
            'registration_closes_at': (now + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 5,
            'price': '0.00',
            'game': self.game.pk,
            'contact_email': 'demo-event@example.com',
        }

    def test_allauth_policy_and_signup_require_email_verification(self):
        self.assertEqual(settings.ACCOUNT_EMAIL_VERIFICATION, 'mandatory')
        self.assertTrue(settings.ACCOUNT_CHANGE_EMAIL)
        self.assertEqual(settings.ACCOUNT_LOGIN_METHODS, {'username', 'email'})

        response = self.client.post(reverse('account_signup'), {
            'terms': 'on',
            'username': 'verification-required',
            'email': 'verification-required@example.com',
            'password1': self.password,
            'password2': self.password,
        })

        user = Player.objects.get(username='verification-required')
        address = EmailAddress.objects.get(user=user)
        self.assertRedirects(
            response,
            reverse('account_email_verification_sent'),
            fetch_redirect_response=False,
        )
        self.assertFalse(address.verified)
        self.assertFalse(get_user(self.client).is_authenticated)
        self.assertEqual(len(mail.outbox), 1)

    def test_normal_user_can_complete_native_password_change(self):
        new_password = 'DifferentStrongPass456!'
        login_response = self.client.post(reverse('account_login'), {
            'login': self.normal.username,
            'password': self.password,
        })
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(get_user(self.client).pk, self.normal.pk)

        change_response = self.client.post(
            reverse('account_change_password'),
            {
                'oldpassword': self.password,
                'password1': new_password,
                'password2': new_password,
            },
        )

        self.assertEqual(change_response.status_code, 302)
        self.normal.refresh_from_db()
        self.assertFalse(self.normal.check_password(self.password))
        self.assertTrue(self.normal.check_password(new_password))
        self.client.logout()
        self.assertFalse(self.client.login(
            username=self.normal.username, password=self.password
        ))
        self.assertTrue(self.client.login(
            username=self.normal.username, password=new_password
        ))

    def test_normal_user_can_complete_native_email_change(self):
        self.client.force_login(self.normal)

        response = self.client.post(reverse('account_email'), {
            'email': 'normal.changed@example.com',
            'action_add': '1',
        })

        self.assertRedirects(
            response, reverse('account_email'), fetch_redirect_response=False
        )
        pending = EmailAddress.objects.get(
            user=self.normal, email='normal.changed@example.com'
        )
        self.assertFalse(pending.primary)
        self.assertFalse(pending.verified)
        self.assertEqual(len(mail.outbox), 1)

        confirmation = EmailConfirmationHMAC.create(pending)
        confirm_response = self.client.post(reverse(
            'account_confirm_email', kwargs={'key': confirmation.key}
        ))

        self.assertEqual(confirm_response.status_code, 302)
        pending.refresh_from_db()
        self.normal.refresh_from_db()
        self.assertTrue(pending.verified)
        self.assertTrue(pending.primary)
        self.assertEqual(self.normal.email, pending.email)
        self.assertEqual(
            EmailAddress.objects.filter(
                user=self.normal, primary=True
            ).count(),
            1,
        )
        self.assertEqual(
            EmailAddress.objects.get(user=self.normal, primary=True).email,
            self.normal.email,
        )

    def test_unverified_user_stays_in_native_verification_flow(self):
        unverified = Player.objects.create_user(
            username='auth-demo-unverified',
            email='unverified@example.com',
            password=self.password,
        )
        EmailAddress.objects.create(
            user=unverified,
            email=unverified.email,
            primary=True,
            verified=False,
        )

        login_response = self.client.post(reverse('account_login'), {
            'login': unverified.username,
            'password': self.password,
        })

        self.assertRedirects(
            login_response,
            reverse('account_email_verification_sent'),
            fetch_redirect_response=False,
        )
        self.assertFalse(get_user(self.client).is_authenticated)

        self.client.force_login(unverified)
        protected_response = self.client.get(reverse('my_events:index'))
        self.assertRedirects(
            protected_response,
            reverse('account_email'),
            fetch_redirect_response=False,
        )

    def test_demo_can_login_through_native_allauth_view(self):
        response = self.client.post(reverse('account_login'), {
            'login': self.demo.username,
            'password': self.password,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_user(self.client).pk, self.demo.pk)

    def test_profile_form_has_no_email_field(self):
        self.assertNotIn('email', ProfileForm(instance=self.normal).fields)

    def test_demo_profile_and_account_screens_are_visible_read_only(self):
        self.client.force_login(self.demo)

        for url_name in (
            'accounts:profile',
            'account_email',
            'account_change_password',
        ):
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Demo account')
                self.assertContains(response, 'read-only')
                self.assertContains(response, 'disabled')

    def test_manipulated_profile_posts_cannot_update_or_delete_demo(self):
        self.client.force_login(self.demo)
        profile_url = reverse('accounts:profile')
        original = (self.demo.username, self.demo.first_name, self.demo.city_id)

        update_response = self.client.post(profile_url, {
            'username': 'manipulated-demo',
            'first_name': 'Changed',
            'last_name': 'Changed',
        })
        delete_response = self.client.post(profile_url, {'_method': 'DELETE'})

        self.demo.refresh_from_db()
        self.assertRedirects(
            update_response, profile_url, fetch_redirect_response=False
        )
        self.assertRedirects(
            delete_response, profile_url, fetch_redirect_response=False
        )
        self.assertEqual(
            (self.demo.username, self.demo.first_name, self.demo.city_id),
            original,
        )
        self.assertTrue(Player.objects.filter(pk=self.demo.pk).exists())

    def test_demo_email_management_blocks_all_exposed_mutations(self):
        pending = EmailAddress.objects.create(
            user=self.demo,
            email='pending-demo@example.com',
            primary=False,
            verified=False,
        )
        self.client.force_login(self.demo)
        email_url = reverse('account_email')

        def email_state():
            return list(EmailAddress.objects.filter(user=self.demo).order_by(
                'email'
            ).values_list('email', 'primary', 'verified'))

        original_state = email_state()
        exposed_mutations = (
            {'email': 'attacker@example.com', 'action_add': '1'},
            {'email': pending.email, 'action_send': '1'},
            {'email': pending.email, 'action_remove': '1'},
        )

        for payload in exposed_mutations:
            with self.subTest(action=next(
                key for key in payload if key.startswith('action_')
            )):
                mail.outbox.clear()
                response = self.client.post(email_url, payload)
                self.assertRedirects(
                    response, email_url, fetch_redirect_response=False
                )
                self.assertEqual(email_state(), original_state)
                self.assertEqual(mail.outbox, [])

    def test_demo_cannot_change_or_set_password_by_direct_post(self):
        self.client.force_login(self.demo)
        old_password = self.demo.password

        password_response = self.client.post(
            reverse('account_change_password'),
            {
                'oldpassword': self.password,
                'password1': 'DifferentStrongPass123!',
                'password2': 'DifferentStrongPass123!',
            },
        )

        self.demo.refresh_from_db()
        self.assertRedirects(
            password_response,
            reverse('account_change_password'),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.demo.password, old_password)

        self.demo.set_unusable_password()
        self.demo.save(update_fields=['password'])
        self.client.force_login(self.demo)
        set_password_response = self.client.post(
            reverse('account_set_password'),
            {
                'password1': 'DifferentStrongPass123!',
                'password2': 'DifferentStrongPass123!',
            },
        )
        self.demo.refresh_from_db()
        self.assertRedirects(
            set_password_response,
            reverse('account_set_password'),
            fetch_redirect_response=False,
        )
        self.assertFalse(self.demo.has_usable_password())

    def test_password_reset_preserves_native_flow_and_anti_enumeration(self):
        outcomes = {}
        for label, email in (
            ('normal', self.normal.email),
            ('demo', self.demo.email),
            ('missing', 'missing-user@example.com'),
        ):
            mail.outbox.clear()
            response = self.client.post(
                reverse('account_reset_password'), {'email': email}
            )
            outcomes[label] = {
                'status': response.status_code,
                'location': response.headers.get('Location'),
                'content': response.content,
                'emails': len(mail.outbox),
            }

        visible_keys = ('status', 'location', 'content')
        self.assertEqual(
            tuple(outcomes['demo'][key] for key in visible_keys),
            tuple(outcomes['missing'][key] for key in visible_keys),
        )
        self.assertEqual(outcomes['demo']['emails'], 0)
        self.assertEqual(outcomes['missing']['emails'], 0)
        self.assertEqual(outcomes['normal']['emails'], 1)
        self.assertEqual(outcomes['normal']['status'], 302)
        self.assertEqual(
            outcomes['normal']['location'],
            reverse('account_reset_password_done'),
        )

    def test_existing_demo_reset_token_is_rejected(self):
        uid = user_pk_to_url_str(self.demo)
        token = default_token_generator.make_token(self.demo)

        response = self.client.get(reverse(
            'account_reset_password_from_key',
            kwargs={'uidb36': uid, 'key': token},
        ))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'invalid', status_code=200)

    def test_demo_email_confirmation_cannot_alter_account(self):
        pending = EmailAddress.objects.create(
            user=self.demo,
            email='pending-demo@example.com',
            primary=False,
            verified=False,
        )
        confirmation = EmailConfirmationHMAC.create(pending)

        response = self.client.post(reverse(
            'account_confirm_email', kwargs={'key': confirmation.key}
        ))

        pending.refresh_from_db()
        self.assertRedirects(
            response, reverse('account_login'), fetch_redirect_response=False
        )
        self.assertFalse(pending.verified)
        self.assertEqual(self.demo.email, 'public-demo@example.com')

    def test_demo_retains_event_and_registration_mutations(self):
        self.client.force_login(self.demo)
        create_response = self.client.post(
            reverse('my_events:create'), self.event_form_data('Created by demo')
        )
        self.assertRedirects(
            create_response,
            reverse('my_events:index'),
            fetch_redirect_response=False,
        )
        owned = Event.objects.get(title='Created by demo')
        self.assertEqual(owned.organizer, self.demo)

        edit_data = self.event_form_data('Edited by demo')
        edit_response = self.client.post(
            reverse('my_events:edit', kwargs={'slug': owned.slug}), edit_data
        )
        self.assertRedirects(
            edit_response,
            reverse('my_events:index'),
            fetch_redirect_response=False,
        )
        owned.refresh_from_db()
        self.assertEqual(owned.title, 'Edited by demo')

        host_event = self.make_event('registration-host')
        register_response = self.client.post(
            reverse('event_register', kwargs={'slug': host_event.slug})
        )
        self.assertEqual(register_response.status_code, 302)
        registration = EventRegistration.objects.get(
            event=host_event, player=self.demo
        )
        cancel_registration_response = self.client.post(reverse(
            'event_cancel_registration', kwargs={'slug': host_event.slug}
        ))
        self.assertEqual(cancel_registration_response.status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(
            registration.status, EventRegistration.Status.CANCELLED
        )

        cancel_response = self.client.post(
            reverse('my_events:cancel', kwargs={'slug': owned.slug})
        )
        self.assertEqual(cancel_response.status_code, 302)
        owned.refresh_from_db()
        self.assertEqual(owned.status, Event.Status.CANCELED)

    def test_demo_organizer_can_see_and_manage_participant_email(self):
        event = self.make_event('participant-email', organizer=self.demo)
        registration = EventRegistration.objects.create(
            event=event, player=self.normal
        )
        self.client.force_login(self.demo)

        detail_response = self.client.get(
            reverse('event_detail', kwargs={'slug': event.slug})
        )
        remove_url = reverse(
            'my_events:remove_participant',
            kwargs={'slug': event.slug, 'reg_id': registration.pk},
        )

        self.assertContains(detail_response, self.normal.username)
        self.assertContains(detail_response, self.normal.email)
        self.assertContains(detail_response, remove_url)

        remove_response = self.client.post(remove_url)

        self.assertEqual(remove_response.status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(
            registration.status, EventRegistration.Status.CANCELLED
        )

    def test_game_status_rejects_javascript_payload(self):
        payload = "' + (window.__xss_probe=1) + '"

        response = self.client.get(
            reverse('games:game_detail', kwargs={'slug': self.game.slug}),
            {'status': payload},
        )

        self.assertEqual(response.context['status'], '')
        self.assertNotContains(response, payload)
        self.assertNotContains(response, 'window.__xss_probe')
        self.assertContains(response, "status: ''")


class SeedUsersVerificationTest(TestCase):
    locations = [
        (2562305, 'Valletta', 'MT'),
        (2510145, 'Trujillo', 'ES'),
        (3176959, 'Florence', 'IT'),
        (2928810, 'Essen', 'DE'),
        (3054643, 'Budapest', 'HU'),
        (3133895, 'Tromso', 'NO'),
        (683506, 'Bucharest', 'RO'),
        (3164603, 'Venice', 'IT'),
        (2638077, 'Sheffield', 'GB'),
        (3169070, 'Rome', 'IT'),
        (2800866, 'Brussels', 'BE'),
        (2643123, 'Manchester', 'GB'),
        (264371, 'Athens', 'GR'),
        (2761369, 'Vienna', 'AT'),
        (3109642, 'Santiago de Compostela', 'ES'),
        (2525068, 'Catania', 'IT'),
        (3096472, 'Katowice', 'PL'),
        (2657896, 'Zurich', 'CH'),
    ]

    def test_all_18_seed_users_are_primary_verified_and_repaired(self):
        countries = {}
        for _, _, country_code in self.locations:
            if country_code not in countries:
                countries[country_code] = Country.objects.create(
                    name=f'{country_code} Country',
                    code2=country_code,
                    code3=f'{country_code}X',
                )
        for geoname_id, city_name, country_code in self.locations:
            City.objects.create(
                name=city_name,
                slug=f'{country_code.lower()}-{geoname_id}',
                geoname_id=geoname_id,
                country=countries[country_code],
            )

        call_command('seed_users', stdout=StringIO())
        EmailAddress.objects.update(verified=False, primary=False)
        call_command('seed_users', stdout=StringIO())

        self.assertEqual(Player.objects.count(), 18)
        self.assertEqual(EmailAddress.objects.count(), 18)
        self.assertEqual(
            EmailAddress.objects.filter(primary=True, verified=True).count(),
            18,
        )
