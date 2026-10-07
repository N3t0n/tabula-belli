from datetime import timedelta

from cities_light.models import City, Country, Region
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event
from apps.games.models import Game
from apps.players.models import Player


class EventListDefensiveFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(
            name="WEB Country", code2="WB", code3="WEB"
        )
        cls.region = Region.objects.create(
            name="WEB Region",
            slug="web-region",
            country=cls.country,
            geoname_id=900001,
        )
        cls.city = City.objects.create(
            name="WEB City",
            slug="web-city",
            country=cls.country,
            region=cls.region,
        )
        cls.other_city = City.objects.create(
            name="WEB Other City",
            slug="web-other-city",
            country=cls.country,
            region=cls.region,
        )
        cls.first_game = Game.objects.create(
            name="WEB First Game",
            slug="web-first-game",
            category=Game.Category.TCG,
        )
        cls.second_game = Game.objects.create(
            name="WEB Second Game",
            slug="web-second-game",
            category=Game.Category.TTRPG,
        )
        organizer = Player.objects.create_user(
            username="web-organizer", email="web@example.test"
        )
        now = timezone.now()
        cls.first_event = Event.objects.create(
            title="WEB First Event",
            slug="web-first-event",
            event_type=Event.EventType.CASUAL,
            country=cls.country,
            region=cls.region,
            city=cls.city,
            game=cls.first_game,
            organizer=organizer,
            contact_email="first@example.test",
            start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=2, hours=2),
            capacity=8,
            price="10.00",
        )
        cls.second_event = Event.objects.create(
            title="WEB Second Event",
            slug="web-second-event",
            event_type=Event.EventType.TOURNAMENT,
            country=cls.country,
            region=cls.region,
            city=cls.other_city,
            game=cls.second_game,
            organizer=organizer,
            contact_email="second@example.test",
            start_at=now + timedelta(days=3),
            end_at=now + timedelta(days=3, hours=2),
            capacity=8,
            price="5.00",
        )
        cls.completed_event = Event.objects.create(
            title="WEB Completed Event",
            slug="web-completed-event",
            status=Event.Status.COMPLETED,
            country=cls.country,
            region=cls.region,
            city=cls.city,
            game=cls.first_game,
            organizer=organizer,
            contact_email="completed@example.test",
            start_at=now - timedelta(days=2),
            end_at=now - timedelta(days=2, hours=-2),
            capacity=8,
        )
        cls.url = reverse("events")

    def event_ids(self, response):
        return {
            event.pk for event in response.context["page_obj"].object_list
        }

    def test_invalid_game_ids_are_ignored(self):
        expected_ids = {self.first_event.pk, self.second_event.pk}

        for value in ["abc", "1.5", "--1", " ", "x" * 256]:
            with self.subTest(value=value):
                response = self.client.get(self.url, {"game_id": value})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.event_ids(response), expected_ids)
                self.assertIsNone(response.context["current_game_id"])

    def test_empty_game_id_is_ignored(self):
        response = self.client.get(self.url, {"game_id": ""})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.event_ids(response),
            {self.first_event.pk, self.second_event.pk},
        )
        self.assertIsNone(response.context["current_game_id"])

    def test_existing_game_id_still_filters(self):
        response = self.client.get(
            self.url, {"game_id": str(self.first_game.pk)}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.event_ids(response), {self.first_event.pk})
        self.assertEqual(
            response.context["current_game_id"], self.first_game.pk
        )

    def test_nonexistent_and_nonpositive_integer_game_ids_are_stable(self):
        for value in ["999999999", "0", "-1"]:
            with self.subTest(value=value):
                response = self.client.get(self.url, {"game_id": value})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.event_ids(response), set())
                self.assertEqual(response.context["current_game_id"], int(value))

    def test_invalid_choice_filters_are_ignored(self):
        for parameter in ["status", "event_type", "category"]:
            with self.subTest(parameter=parameter):
                response = self.client.get(self.url, {parameter: "unknown"})
                expected_ids = {
                    self.first_event.pk,
                    self.second_event.pk,
                }
                if parameter == "status":
                    expected_ids.add(self.completed_event.pk)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.event_ids(response), expected_ids)
                self.assertEqual(response.context[f"current_{parameter}"], "")

    def test_valid_status_and_sort_still_apply(self):
        status_response = self.client.get(self.url, {"status": "completed"})
        sort_response = self.client.get(self.url, {"sort": "-price"})

        self.assertEqual(
            self.event_ids(status_response), {self.completed_event.pk}
        )
        self.assertEqual(status_response.context["current_status"], "completed")
        self.assertEqual(
            list(sort_response.context["page_obj"].object_list),
            [self.first_event, self.second_event],
        )
        self.assertEqual(sort_response.context["current_sort"], "-price")

    def test_other_valid_filters_still_apply(self):
        cases = [
            ("event_type", Event.EventType.TOURNAMENT, {self.second_event.pk}),
            ("category", Game.Category.TCG, {self.first_event.pk}),
            ("region", str(self.region.geoname_id), {
                self.first_event.pk, self.second_event.pk
            }),
            ("city", str(self.city.pk), {self.first_event.pk}),
        ]

        for parameter, value, expected_ids in cases:
            with self.subTest(parameter=parameter):
                response = self.client.get(self.url, {parameter: value})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.event_ids(response), expected_ids)

    def test_invalid_sort_uses_default_order(self):
        response = self.client.get(self.url, {"sort": "arbitrary"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["page_obj"].object_list),
            [self.first_event, self.second_event],
        )
        self.assertEqual(response.context["current_sort"], "start_at")

    def test_invalid_location_ids_are_ignored(self):
        expected_ids = {self.first_event.pk, self.second_event.pk}

        for parameter in ["region", "city"]:
            for value in ["abc", "1.5", "--1", " ", "x" * 256]:
                with self.subTest(parameter=parameter, value=value):
                    response = self.client.get(self.url, {parameter: value})

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(self.event_ids(response), expected_ids)
                    self.assertEqual(
                        response.context[f"current_{parameter}"], ""
                    )

    def test_htmx_uses_partial_and_drops_invalid_filters_from_url(self):
        response = self.client.get(
            self.url,
            {
                "game_id": "abc",
                "status": "unknown",
                "sort": "arbitrary",
                "region": "1.5",
                "city": "--1",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/_events_listing.html")
        self.assertEqual(response.headers["HX-Replace-Url"], self.url)
        self.assertNotContains(response, "<!DOCTYPE html>")

    def test_htmx_preserves_valid_game_filter_in_url(self):
        response = self.client.get(
            self.url,
            {"game_id": str(self.first_game.pk)},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["HX-Replace-Url"],
            f"{self.url}?game_id={self.first_game.pk}",
        )
        self.assertEqual(self.event_ids(response), {self.first_event.pk})

    def test_pagination_keeps_django_standard_behavior(self):
        for value in ["abc", "-1", "0", "999999999"]:
            with self.subTest(value=value):
                response = self.client.get(self.url, {"page": value})
                self.assertEqual(response.status_code, 404)

        empty_response = self.client.get(self.url, {"page": ""})
        self.assertEqual(empty_response.status_code, 200)
        self.assertEqual(empty_response.context["page_obj"].number, 1)
