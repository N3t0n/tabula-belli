from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from apps.events.models import Event
from apps.games.models import Game
from apps.players.models import Player
from cities_light.models import City, Country


class EventDetailSafeReturnUrlTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        country = Country.objects.create(
            name='Spain',
            name_ascii='Spain',
            slug='spain',
            geoname_id=2510769,
            code2='ES',
            code3='ESP',
            continent='EU',
            tld='.es',
            phone='34',
        )
        city = City.objects.create(
            name='Madrid',
            name_ascii='Madrid',
            slug='madrid',
            geoname_id=3117735,
            display_name='Madrid, Spain',
            country=country,
        )
        organizer = Player.objects.create_user(
            username='sec002-organizer',
            email='sec002@example.test',
            password='test-only-password',
        )
        game = Game.objects.create(
            name='SEC-002 Test Game',
            category=Game.Category.WARGAME,
            is_official=True,
        )
        now = timezone.now()
        cls.event = Event.objects.create(
            title='SEC-002 Test Event',
            slug='sec-002-test-event',
            event_type=Event.EventType.CASUAL,
            status=Event.Status.ACTIVE,
            start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=2, hours=2),
            capacity=10,
            country=country,
            city=city,
            game=game,
            organizer=organizer,
            contact_email=organizer.email,
        )
        cls.detail_url = reverse('event_detail', args=[cls.event.slug])
        cls.fallback_url = reverse('events')

    def assert_return_url(self, supplied_url, expected_url):
        query = {} if supplied_url is None else {'return': supplied_url}

        response = self.client.get(self.detail_url, query)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['return_url'], expected_url)
        self.assertContains(response, f'href="{escape(expected_url)}"')
        if supplied_url and supplied_url != expected_url:
            self.assertNotContains(response, f'href="{escape(supplied_url)}"')

    def test_missing_return_uses_events_fallback(self):
        self.assert_return_url(None, self.fallback_url)

    def test_local_path_preserves_query_string(self):
        local_url = '/events/?page=2&status=completed'
        self.assert_return_url(local_url, local_url)

    def test_same_host_absolute_url_is_allowed(self):
        local_url = 'http://testserver/events/?page=2'
        self.assert_return_url(local_url, local_url)

    def test_javascript_scheme_is_rejected(self):
        self.assert_return_url('javascript:alert(1)', self.fallback_url)

    def test_data_scheme_is_rejected(self):
        self.assert_return_url('data:text/html,unsafe', self.fallback_url)

    def test_protocol_relative_external_url_is_rejected(self):
        self.assert_return_url('//evil.example/path', self.fallback_url)

    def test_http_external_url_is_rejected(self):
        self.assert_return_url('http://evil.example/path', self.fallback_url)

    def test_https_external_url_is_rejected(self):
        self.assert_return_url('https://evil.example/path', self.fallback_url)

    def test_backslash_external_url_is_rejected(self):
        self.assert_return_url(r'\\evil.example\path', self.fallback_url)
