from datetime import timedelta

from cities_light.models import City, Country, Region
from django.db import connection
from django.db.models import Count, Q
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventRegistration
from apps.events.views import EventListView
from apps.games.models import Game
from apps.players.models import Player


class EventQueryPerformanceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(
            name="PERF Country", code2="PF", code3="PRF"
        )
        cls.region = Region.objects.create(
            name="PERF Region",
            slug="perf-region",
            country=cls.country,
            geoname_id=910001,
        )
        cls.first_city = City.objects.create(
            name="PERF First City",
            slug="perf-first-city",
            country=cls.country,
            region=cls.region,
        )
        cls.second_city = City.objects.create(
            name="PERF Second City",
            slug="perf-second-city",
            country=cls.country,
            region=cls.region,
        )
        cls.first_game = Game.objects.create(
            name="PERF First Game",
            slug="perf-first-game",
            category=Game.Category.TCG,
        )
        cls.second_game = Game.objects.create(
            name="PERF Second Game",
            slug="perf-second-game",
            category=Game.Category.TTRPG,
        )
        cls.organizer = Player.objects.create_user(
            username="perf-organizer", email="perf-organizer@example.test"
        )
        cls.participant = Player.objects.create_user(
            username="perf-participant", email="perf-participant@example.test"
        )
        cls.first_event = cls.create_event(1, capacity=1)
        cls.second_event = cls.create_event(
            2, city=cls.second_city, game=cls.second_game
        )
        EventRegistration.objects.create(
            event=cls.first_event,
            player=cls.participant,
            status=EventRegistration.Status.CONFIRMED,
        )

    @classmethod
    def create_event(cls, index, capacity=8, city=None, game=None):
        now = timezone.now()
        return Event.objects.create(
            title=f"PERF Event {index}",
            slug=f"perf-event-{index}",
            event_type=Event.EventType.CASUAL,
            country=cls.country,
            region=cls.region,
            city=city or cls.first_city,
            game=game or cls.first_game,
            organizer=cls.organizer,
            contact_email="perf@example.test",
            start_at=now + timedelta(days=index + 1),
            end_at=now + timedelta(days=index + 1, hours=2),
            capacity=capacity,
        )

    def test_registration_status_reuses_annotation_with_query_fallback(self):
        unannotated_event = Event.objects.get(pk=self.first_event.pk)
        with CaptureQueriesContext(connection) as fallback_queries:
            fallback_status = unannotated_event.get_registration_status()

        annotated_event = Event.objects.annotate(
            participants_count=Count(
                "registrations",
                filter=Q(
                    registrations__status=EventRegistration.Status.CONFIRMED
                ),
                distinct=True,
            )
        ).get(pk=self.first_event.pk)
        with CaptureQueriesContext(connection) as annotated_queries:
            annotated_status = annotated_event.get_registration_status()

        self.assertEqual(fallback_status, Event.RegistrationStatus.FULL)
        self.assertEqual(annotated_status, fallback_status)
        self.assertEqual(len(fallback_queries), 1)
        self.assertEqual(len(annotated_queries), 0)

    def test_event_list_query_count_does_not_grow_per_event(self):
        url = reverse("events")

        with CaptureQueriesContext(connection) as small_page_queries:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

        for index in range(3, 13):
            self.create_event(index)

        with CaptureQueriesContext(connection) as full_page_queries:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

        # Eight page queries plus four fixed maintenance-lock queries.
        self.assertEqual(len(small_page_queries), 12)
        self.assertEqual(len(full_page_queries), len(small_page_queries))

    def test_availability_facets_are_unique_in_four_queries(self):
        request = RequestFactory().get(reverse("events"))
        view = EventListView()
        view.setup(request)

        with CaptureQueriesContext(connection) as facet_queries:
            availability = view._get_availability_sets()

        self.assertEqual(len(facet_queries), 4)
        self.assertTrue(all(
            "SELECT DISTINCT" in query["sql"].upper()
            for query in facet_queries
        ))
        self.assertEqual(
            availability["available_countries"], {self.country.code2}
        )
        self.assertEqual(
            availability["available_regions"], {self.region.geoname_id}
        )
        self.assertEqual(
            availability["available_cities"],
            {self.first_city.pk, self.second_city.pk},
        )
        self.assertEqual(
            availability["available_games"],
            {self.first_game.pk, self.second_game.pk},
        )
