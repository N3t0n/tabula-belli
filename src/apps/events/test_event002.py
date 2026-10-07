from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from allauth.account.models import EmailAddress
from cities_light.models import City, Country, Region
from django.core.exceptions import ValidationError
from django.db import (
    IntegrityError,
    OperationalError,
    close_old_connections,
    connection,
)
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventRegistration
from apps.events.services import cancel_event
from apps.games.models import Game
from apps.players.models import Player


class EventCancellationFixtureMixin:
    def setUp(self):
        super().setUp()
        country = Country.objects.create(
            name="Cancellation Country", code2="CC", code3="CCN"
        )
        region = Region.objects.create(
            name="Cancellation Region",
            slug="cancellation-region",
            country=country,
        )
        city = City.objects.create(
            name="Cancellation City",
            slug="cancellation-city",
            region=region,
            country=country,
        )
        game = Game.objects.create(
            name="Cancellation Game",
            slug="cancellation-game",
            category=Game.Category.TCG,
        )
        self.organizer = Player.objects.create_user(
            username="cancellation-organizer",
            email="organizer@cancellation.test",
        )
        self.other_user = Player.objects.create_user(
            username="cancellation-other-user",
            email="other@cancellation.test",
        )
        self.players = [
            Player.objects.create_user(
                username=f"cancellation-player-{index}",
                email=f"player-{index}@cancellation.test",
            )
            for index in range(4)
        ]
        EmailAddress.objects.bulk_create([
            EmailAddress(
                user=user,
                email=user.email,
                primary=True,
                verified=True,
            )
            for user in [self.organizer, self.other_user, *self.players]
        ])
        self.event_fields = {
            "country": country,
            "city": city,
            "game": game,
            "organizer": self.organizer,
            "contact_email": "event@cancellation.test",
            "capacity": 10,
        }

    def create_event(self, slug, *, status=Event.Status.ACTIVE):
        now = timezone.now()
        if status == Event.Status.COMPLETED:
            start_at = now - timedelta(days=2)
            end_at = now - timedelta(days=2, hours=-2)
        else:
            start_at = now + timedelta(days=2)
            end_at = now + timedelta(days=2, hours=2)

        return Event.objects.create(
            title=slug,
            slug=slug,
            status=status,
            start_at=start_at,
            end_at=end_at,
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=1),
            **self.event_fields,
        )

    def create_confirmed(self, event, player):
        return EventRegistration.objects.create(
            event=event,
            player=player,
            status=EventRegistration.Status.CONFIRMED,
        )


class EventCancellationServiceTest(EventCancellationFixtureMixin, TestCase):
    def test_cancels_active_event_without_registrations(self):
        event = self.create_event("cancel-empty")

        cancel_event(event)

        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CANCELED)
        self.assertEqual(event.registrations.count(), 0)

    def test_cancels_single_confirmed_registration(self):
        event = self.create_event("cancel-single")
        registration = self.create_confirmed(event, self.players[0])

        cancel_event(event)

        event.refresh_from_db()
        registration.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CANCELED)
        self.assertEqual(
            registration.status, EventRegistration.Status.CANCELLED
        )
        self.assertIsNotNone(registration.cancelled_at)
        self.assertFalse(
            event.registrations.filter(
                status=EventRegistration.Status.CONFIRMED
            ).exists()
        )

    def test_cancels_all_confirmed_registrations_with_one_timestamp(self):
        event = self.create_event("cancel-many")
        registrations = [
            self.create_confirmed(event, player)
            for player in self.players[:3]
        ]

        cancel_event(event)

        for registration in registrations:
            registration.refresh_from_db()
        self.assertTrue(
            all(
                registration.status == EventRegistration.Status.CANCELLED
                for registration in registrations
            )
        )
        self.assertEqual(
            len({registration.cancelled_at for registration in registrations}),
            1,
        )
        self.assertFalse(
            event.registrations.filter(
                status=EventRegistration.Status.CONFIRMED
            ).exists()
        )

    def test_preserves_previously_cancelled_registration_history(self):
        event = self.create_event("cancel-mixed")
        confirmed = self.create_confirmed(event, self.players[0])
        original_cancelled_at = timezone.now() - timedelta(days=10)
        historical = EventRegistration.objects.create(
            event=event,
            player=self.players[1],
            status=EventRegistration.Status.CANCELLED,
            cancelled_at=original_cancelled_at,
        )
        historical_updated_at = historical.updated_at

        cancel_event(event)

        confirmed.refresh_from_db()
        historical.refresh_from_db()
        self.assertEqual(
            confirmed.status, EventRegistration.Status.CANCELLED
        )
        self.assertEqual(
            historical.status, EventRegistration.Status.CANCELLED
        )
        self.assertEqual(historical.cancelled_at, original_cancelled_at)
        self.assertEqual(historical.updated_at, historical_updated_at)
        self.assertEqual(event.registrations.count(), 2)

    def test_rejects_already_cancelled_event(self):
        event = self.create_event(
            "already-cancelled", status=Event.Status.CANCELED
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Cannot cancel this event because it has status Canceled",
        ):
            cancel_event(event)

    def test_rejects_completed_event(self):
        event = self.create_event(
            "already-completed", status=Event.Status.COMPLETED
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Cannot cancel this event because it has status Completed",
        ):
            cancel_event(event)

    def test_rolls_back_registrations_when_event_save_fails(self):
        event = self.create_event("cancel-rollback")
        registrations = [
            self.create_confirmed(event, player)
            for player in self.players[:2]
        ]

        with patch.object(
            Event, "save", side_effect=RuntimeError("forced event save failure")
        ):
            with self.assertRaisesMessage(
                RuntimeError, "forced event save failure"
            ):
                cancel_event(event)

        event.refresh_from_db()
        for registration in registrations:
            registration.refresh_from_db()
        self.assertEqual(event.status, Event.Status.ACTIVE)
        self.assertTrue(
            all(
                registration.status == EventRegistration.Status.CONFIRMED
                and registration.cancelled_at is None
                for registration in registrations
            )
        )


class EventCancellationHttpTest(EventCancellationFixtureMixin, TestCase):
    def test_authorized_post_cancels_event_and_registrations(self):
        event = self.create_event("cancel-http")
        registration = self.create_confirmed(event, self.players[0])
        self.client.force_login(self.organizer)

        response = self.client.post(
            reverse("my_events:cancel", kwargs={"slug": event.slug}),
            HTTP_HX_REQUEST="true",
        )

        event.refresh_from_db()
        registration.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["HX-Redirect"], reverse("my_events:index"))
        self.assertEqual(event.status, Event.Status.CANCELED)
        self.assertEqual(
            registration.status, EventRegistration.Status.CANCELLED
        )
        self.assertFalse(
            event.registrations.filter(
                status=EventRegistration.Status.CONFIRMED
            ).exists()
        )

    def test_unauthorized_post_preserves_existing_behavior(self):
        event = self.create_event("cancel-http-forbidden")
        registration = self.create_confirmed(event, self.players[0])
        self.client.force_login(self.other_user)

        response = self.client.post(
            reverse("my_events:cancel", kwargs={"slug": event.slug})
        )

        event.refresh_from_db()
        registration.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(event.status, Event.Status.ACTIVE)
        self.assertEqual(
            registration.status, EventRegistration.Status.CONFIRMED
        )


class EventCancellationConcurrencyTest(
    EventCancellationFixtureMixin, TransactionTestCase
):
    reset_sequences = True

    def _attempt_cancellation(self, event_id, barrier):
        close_old_connections()
        try:
            event = Event.objects.get(pk=event_id)
            barrier.wait(timeout=10)
            cancel_event(event)
            return "canceled", None
        except (ValidationError, IntegrityError, OperationalError) as error:
            return error.__class__.__name__, str(error)
        finally:
            connection.close()

    def _attempt_registration(self, event_id, player_id, barrier):
        close_old_connections()
        try:
            event = Event.objects.get(pk=event_id)
            player = Player.objects.get(pk=player_id)
            barrier.wait(timeout=10)
            registration = EventRegistration.register(
                event=event, player=player
            )
            return "created", registration.pk
        except ValidationError as error:
            return "conflict", error.messages[0]
        except (IntegrityError, OperationalError) as error:
            return error.__class__.__name__, str(error)
        finally:
            connection.close()

    @skipUnlessDBFeature("has_select_for_update")
    def test_cancel_vs_register_preserves_canceled_event_invariant(self):
        event = self.create_event("cancel-vs-register")
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            cancellation = executor.submit(
                self._attempt_cancellation, event.pk, barrier
            )
            registration = executor.submit(
                self._attempt_registration,
                event.pk,
                self.players[0].pk,
                barrier,
            )
            cancellation_result = cancellation.result(timeout=20)
            registration_result = registration.result(timeout=20)

        event.refresh_from_db()
        self.assertEqual(cancellation_result, ("canceled", None))
        self.assertIn(registration_result[0], {"created", "conflict"})
        if registration_result[0] == "created":
            concurrent_registration = EventRegistration.objects.get(
                pk=registration_result[1]
            )
            self.assertEqual(
                concurrent_registration.status,
                EventRegistration.Status.CANCELLED,
            )
            self.assertIsNotNone(concurrent_registration.cancelled_at)
        else:
            self.assertIn("canceled event", registration_result[1])
        self.assertEqual(event.status, Event.Status.CANCELED)
        self.assertFalse(
            event.registrations.filter(
                status=EventRegistration.Status.CONFIRMED
            ).exists()
        )
