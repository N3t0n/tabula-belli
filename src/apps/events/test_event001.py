from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from allauth.account.models import EmailAddress
from cities_light.models import City, Country, Region
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event
from apps.games.models import Game
from apps.players.models import Player


class EventLifecycleFixtureMixin:
    def setUp(self):
        super().setUp()
        country = Country.objects.create(
            name="Lifecycle Country", code2="LC", code3="LCY"
        )
        region = Region.objects.create(
            name="Lifecycle Region",
            slug="lifecycle-region",
            country=country,
        )
        city = City.objects.create(
            name="Lifecycle City",
            slug="lifecycle-city",
            region=region,
            country=country,
        )
        game = Game.objects.create(
            name="Lifecycle Game",
            slug="lifecycle-game",
            category=Game.Category.TCG,
        )
        self.organizer = Player.objects.create_user(
            username="lifecycle-organizer",
            email="organizer@lifecycle.test",
        )
        EmailAddress.objects.create(
            user=self.organizer,
            email=self.organizer.email,
            primary=True,
            verified=True,
        )
        self.event_fields = {
            "country": country,
            "city": city,
            "game": game,
            "organizer": self.organizer,
            "contact_email": "event@lifecycle.test",
            "capacity": 2,
        }

    def create_event(self, slug, *, status, end_at):
        return Event.objects.create(
            title=slug,
            slug=slug,
            status=status,
            start_at=end_at - timedelta(hours=2),
            end_at=end_at,
            **self.event_fields,
        )

    def set_known_updated_at(self, event):
        known_updated_at = timezone.now() - timedelta(days=30)
        Event.objects.filter(pk=event.pk).update(
            updated_at=known_updated_at
        )
        event.refresh_from_db()
        return event.updated_at


class EventListReadOnlyTest(EventLifecycleFixtureMixin, TestCase):
    def test_event_list_get_does_not_complete_past_active_event(self):
        event = self.create_event(
            "past-active-event-list",
            status=Event.Status.ACTIVE,
            end_at=timezone.now() - timedelta(days=1),
        )
        original_updated_at = self.set_known_updated_at(event)

        with patch(
            "apps.events.services.complete_past_events"
        ) as complete_mock:
            response = self.client.get(reverse("events"))

        event.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(event.status, Event.Status.ACTIVE)
        self.assertEqual(event.updated_at, original_updated_at)
        complete_mock.assert_not_called()

    def test_my_events_get_does_not_complete_past_active_event(self):
        event = self.create_event(
            "past-active-my-events",
            status=Event.Status.ACTIVE,
            end_at=timezone.now() - timedelta(days=1),
        )
        original_updated_at = self.set_known_updated_at(event)
        self.client.force_login(self.organizer)

        with patch(
            "apps.events.services.complete_past_events"
        ) as complete_mock:
            response = self.client.get(reverse("my_events:index"))

        event.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(event.status, Event.Status.ACTIVE)
        self.assertEqual(event.updated_at, original_updated_at)
        complete_mock.assert_not_called()


class CompletePastEventsCommandTest(EventLifecycleFixtureMixin, TestCase):
    def test_command_completes_only_past_active_events(self):
        now = timezone.now()
        past_active = self.create_event(
            "past-active-command",
            status=Event.Status.ACTIVE,
            end_at=now - timedelta(days=1),
        )
        future_active = self.create_event(
            "future-active-command",
            status=Event.Status.ACTIVE,
            end_at=now + timedelta(days=1),
        )
        past_canceled = self.create_event(
            "past-canceled-command",
            status=Event.Status.CANCELED,
            end_at=now - timedelta(days=1),
        )
        already_completed = self.create_event(
            "already-completed-command",
            status=Event.Status.COMPLETED,
            end_at=now - timedelta(days=1),
        )
        unchanged_updated_at = {
            event.pk: self.set_known_updated_at(event)
            for event in (future_active, past_canceled, already_completed)
        }

        stdout = StringIO()
        call_command("complete_past_events", stdout=stdout)

        for event in (
            past_active,
            future_active,
            past_canceled,
            already_completed,
        ):
            event.refresh_from_db()

        self.assertEqual(past_active.status, Event.Status.COMPLETED)
        self.assertEqual(future_active.status, Event.Status.ACTIVE)
        self.assertEqual(past_canceled.status, Event.Status.CANCELED)
        self.assertEqual(already_completed.status, Event.Status.COMPLETED)
        self.assertIn("Completed 1 past events", stdout.getvalue())
        for event in (future_active, past_canceled, already_completed):
            self.assertEqual(
                event.updated_at, unchanged_updated_at[event.pk]
            )

    def test_command_is_idempotent(self):
        event = self.create_event(
            "past-active-idempotent",
            status=Event.Status.ACTIVE,
            end_at=timezone.now() - timedelta(days=1),
        )

        first_stdout = StringIO()
        call_command("complete_past_events", stdout=first_stdout)
        event.refresh_from_db()
        first_completed_at = event.updated_at

        second_stdout = StringIO()
        call_command("complete_past_events", stdout=second_stdout)
        event.refresh_from_db()

        self.assertEqual(event.status, Event.Status.COMPLETED)
        self.assertEqual(event.updated_at, first_completed_at)
        self.assertIn("Completed 1 past events", first_stdout.getvalue())
        self.assertIn(
            "No past events to complete", second_stdout.getvalue()
        )
