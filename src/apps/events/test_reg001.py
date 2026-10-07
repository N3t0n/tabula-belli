from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from allauth.account.models import EmailAddress
from cities_light.models import City, Country, Region
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventRegistration
from apps.games.models import Game
from apps.players.models import Player


class RegistrationFixtureMixin:
    def setUp(self):
        super().setUp()
        country = Country.objects.create(
            name="Registration Country", code2="RG", code3="REG"
        )
        region = Region.objects.create(
            name="Registration Region",
            slug="registration-region",
            country=country,
        )
        city = City.objects.create(
            name="Registration City",
            slug="registration-city",
            region=region,
            country=country,
        )
        game = Game.objects.create(
            name="Registration Game",
            slug="registration-game",
            category=Game.Category.TCG,
        )
        self.organizer = Player.objects.create_user(
            username="registration-organizer",
            email="organizer@registration.test",
        )
        self.player = Player.objects.create_user(
            username="registration-player",
            email="player@registration.test",
        )
        self.other_player = Player.objects.create_user(
            username="registration-other-player",
            email="other-player@registration.test",
        )
        EmailAddress.objects.bulk_create([
            EmailAddress(
                user=user,
                email=user.email,
                primary=True,
                verified=True,
            )
            for user in (self.organizer, self.player, self.other_player)
        ])
        now = timezone.now()
        self.event = Event.objects.create(
            title="Registration Event",
            slug="registration-event",
            country=country,
            city=city,
            game=game,
            organizer=self.organizer,
            contact_email="event@registration.test",
            start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=2, hours=2),
            capacity=2,
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=1),
        )


class EventRegistrationRegisterTest(RegistrationFixtureMixin, TestCase):
    def test_registers_player_when_capacity_is_available(self):
        registration = EventRegistration.register(
            event=self.event, player=self.player
        )

        self.assertEqual(registration.status, EventRegistration.Status.CONFIRMED)
        self.assertEqual(registration.event, self.event)
        self.assertEqual(registration.player, self.player)

    def test_full_event_raises_domain_error(self):
        self.event.capacity = 1
        self.event.save(update_fields=["capacity"])
        EventRegistration.objects.create(
            event=self.event,
            player=self.other_player,
            status=EventRegistration.Status.CONFIRMED,
        )

        with self.assertRaisesMessage(ValidationError, "Event is full"):
            EventRegistration.register(event=self.event, player=self.player)

    def test_sequential_duplicate_raises_domain_error(self):
        EventRegistration.register(event=self.event, player=self.player)

        with self.assertRaisesMessage(
            ValidationError, "You are already registered for this event"
        ):
            EventRegistration.register(event=self.event, player=self.player)

        self.assertEqual(
            EventRegistration.objects.filter(
                event=self.event,
                player=self.player,
                status=EventRegistration.Status.CONFIRMED,
            ).count(),
            1,
        )

    def test_cancelled_registration_can_be_replaced(self):
        cancelled = EventRegistration.register(
            event=self.event, player=self.player
        )
        cancelled.cancel()

        replacement = EventRegistration.register(
            event=self.event, player=self.player
        )

        self.assertEqual(cancelled.status, EventRegistration.Status.CANCELLED)
        self.assertEqual(replacement.status, EventRegistration.Status.CONFIRMED)
        self.assertNotEqual(cancelled.pk, replacement.pk)

    def test_duplicate_post_returns_controlled_http_400(self):
        EventRegistration.register(event=self.event, player=self.player)
        self.client.force_login(self.player)

        response = self.client.post(
            reverse("event_register", kwargs={"slug": self.event.slug}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "You are already registered for this event",
            status_code=400,
        )

    def test_expected_unique_conflict_becomes_domain_error(self):
        error = IntegrityError("expected unique conflict")
        cause = Exception("database constraint violation")
        cause.diag = SimpleNamespace(
            constraint_name="unique_active_registration"
        )
        error.__cause__ = cause

        with patch.object(
            EventRegistration.objects, "create", side_effect=error
        ):
            with self.assertRaisesMessage(
                ValidationError, "You are already registered for this event"
            ):
                EventRegistration.register(
                    event=self.event, player=self.player
                )

    def test_unrelated_integrity_error_is_not_hidden(self):
        with patch.object(
            EventRegistration.objects,
            "create",
            side_effect=IntegrityError("unrelated integrity failure"),
        ):
            with self.assertRaisesMessage(
                IntegrityError, "unrelated integrity failure"
            ):
                EventRegistration.register(
                    event=self.event, player=self.player
                )


class EventRegistrationConcurrencyTest(
    RegistrationFixtureMixin, TransactionTestCase
):
    reset_sequences = True

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
        except IntegrityError as error:
            return "integrity_error", str(error)
        finally:
            connection.close()

    def _run_concurrent_registrations(self, player_ids):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self._attempt_registration,
                    self.event.pk,
                    player_id,
                    barrier,
                )
                for player_id in player_ids
            ]
            return [future.result(timeout=20) for future in futures]

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_distinct_players_do_not_exceed_capacity(self):
        self.event.capacity = 1
        self.event.save(update_fields=["capacity"])

        results = self._run_concurrent_registrations(
            [self.player.pk, self.other_player.pk]
        )

        self.assertCountEqual(
            [result[0] for result in results], ["created", "conflict"]
        )
        self.assertEqual(
            EventRegistration.objects.filter(
                event=self.event,
                status=EventRegistration.Status.CONFIRMED,
            ).count(),
            1,
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_same_player_returns_controlled_conflict(self):
        results = self._run_concurrent_registrations(
            [self.player.pk, self.player.pk]
        )

        self.assertCountEqual(
            [result[0] for result in results], ["created", "conflict"]
        )
        self.assertEqual(
            EventRegistration.objects.filter(
                event=self.event,
                player=self.player,
                status=EventRegistration.Status.CONFIRMED,
            ).count(),
            1,
        )
