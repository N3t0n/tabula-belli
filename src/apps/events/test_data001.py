import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from allauth.account.models import EmailAddress
from cities_light.models import City, Country
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.events.models import Event, EventRegistration
from apps.games.models import Game
from apps.players.models import Player


class DeterministicSeedTest(TestCase):
    seed_password = 'TestPass123!'

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        (self.project_root / 'fixtures').mkdir()
        self.settings_override = override_settings(
            BASE_DIR=self.project_root / 'src',
        )
        self.settings_override.enable()

        self.countries = {}
        for code2, code3, name in [
            ('BE', 'BEL', 'Belgium'),
            ('BY', 'BLR', 'Belarus'),
            ('DE', 'DEU', 'Germany'),
            ('ES', 'ESP', 'Spain'),
            ('FR', 'FRA', 'France'),
            ('GB', 'GBR', 'United Kingdom'),
            ('MT', 'MLT', 'Malta'),
            ('NL', 'NLD', 'Netherlands'),
            ('NO', 'NOR', 'Norway'),
            ('RS', 'SRB', 'Serbia'),
        ]:
            self.countries[code2] = Country.objects.create(
                name=name,
                code2=code2,
                code3=code3,
            )

        city_specs = [
            ('Belgrade', 'BE', 2802359),
            ('Belgrade', 'RS', 792680),
            ('Bergen', 'DE', 2950622),
            ('Bergen', 'NO', 3161732),
            ('Breda', 'ES', 3127655),
            ('Breda', 'NL', 2758401),
            ('Essen', 'BE', 2798615),
            ('Essen', 'DE', 2928810),
            ('Hove', 'BE', 2795232),
            ('Hove', 'GB', 2646504),
            ('Brest', 'BY', 629634),
            ('Brest', 'FR', 3030300),
            ('Valletta', 'MT', 2562305),
        ]
        for name, country_code, geoname_id in city_specs:
            City.objects.create(
                name=name,
                name_ascii=name,
                country=self.countries[country_code],
                geoname_id=geoname_id,
            )

        self.game = Game.objects.create(
            name='DATA Game',
            slug='data-game',
            category=Game.Category.TCG,
        )
        self.players = [
            Player.objects.create_user(
                username=f'data-player-{index}',
                email=f'data-player-{index}@example.com',
                password=self.seed_password,
            )
            for index in range(1, 6)
        ]
        self.base_date = timezone.localdate()

    def tearDown(self):
        self.settings_override.disable()
        self.temp_dir.cleanup()

    def event_data(
        self,
        slug,
        city,
        country_code,
        city_geoname_id,
        title=None,
    ):
        return {
            'title': title or f'DATA Event {slug}',
            'slug': slug,
            'event_type': Event.EventType.CASUAL,
            'description': 'Deterministic seed test event',
            'start_offset_days': 10,
            'start_time_hour': 10,
            'start_time_minute': 0,
            'end_offset_days': 10,
            'end_time_hour': 12,
            'end_time_minute': 0,
            'registration_opens_offset_days': 0,
            'registration_opens_time_hour': 0,
            'registration_opens_time_minute': 0,
            'registration_closes_offset_days': 9,
            'registration_closes_time_hour': 10,
            'registration_closes_time_minute': 0,
            'capacity': 5,
            'price': '10.00',
            'location_name': f'{city} Demo Venue',
            'location_address': f'Demo address in {city}',
            'city': city,
            'country_code': country_code,
            'city_geoname_id': city_geoname_id,
            'game': self.game.name,
        }

    def known_city_events(self):
        return [
            self.event_data('data-belgrade', 'Belgrade', 'RS', 792680),
            self.event_data('data-bergen', 'Bergen', 'NO', 3161732),
            self.event_data('data-breda', 'Breda', 'NL', 2758401),
            self.event_data('data-essen', 'Essen', 'DE', 2928810),
            self.event_data('data-hove', 'Hove', 'GB', 2646504),
            self.event_data('data-brest-by', 'Brest', 'BY', 629634),
            self.event_data('data-brest-fr', 'Brest', 'FR', 3030300),
        ]

    def write_fixture(self, events, filename='data001.json'):
        fixture_path = self.project_root / 'fixtures' / filename
        fixture_path.write_text(
            json.dumps(events, ensure_ascii=False),
            encoding='utf-8',
        )
        return filename

    def seed_events(self, filename='data001.json', seed=42, clear=False):
        call_command(
            'seed_events',
            file=filename,
            seed=seed,
            base_date=self.base_date,
            clear=clear,
            stdout=StringIO(),
        )

    @staticmethod
    def event_fingerprint():
        return list(Event.objects.order_by('slug').values_list(
            'slug',
            'title',
            'organizer__username',
            'city__geoname_id',
            'country__code2',
            'start_at',
            'end_at',
            'capacity',
            'price',
            'status',
        ))

    @staticmethod
    def registration_fingerprint():
        return list(EventRegistration.objects.order_by(
            'event__slug', 'player__username'
        ).values_list(
            'event__slug',
            'player__username',
            'status',
        ))

    def test_seed_events_twice_preserves_count_and_content(self):
        events = self.known_city_events()
        self.write_fixture(events)

        self.seed_events(seed=77)
        first_fingerprint = self.event_fingerprint()
        self.seed_events(seed=77)

        self.assertEqual(Event.objects.count(), len(events))
        self.assertEqual(self.event_fingerprint(), first_fingerprint)

    def test_same_seed_rebuilds_same_randomized_event_content(self):
        self.write_fixture(self.known_city_events())

        self.seed_events(seed=91, clear=True)
        first_fingerprint = self.event_fingerprint()
        self.seed_events(seed=91, clear=True)

        self.assertEqual(self.event_fingerprint(), first_fingerprint)

    def test_seed_registrations_twice_is_idempotent(self):
        self.write_fixture(self.known_city_events())
        self.seed_events(seed=13)

        call_command('seed_registrations', seed=13, stdout=StringIO())
        first_fingerprint = self.registration_fingerprint()
        call_command('seed_registrations', seed=13, stdout=StringIO())

        self.assertGreater(len(first_fingerprint), 0)
        self.assertEqual(
            self.registration_fingerprint(),
            first_fingerprint,
        )
        duplicates = EventRegistration.objects.filter(
            status=EventRegistration.Status.CONFIRMED,
        ).values('event', 'player').annotate(total=Count('pk')).filter(total__gt=1)
        self.assertFalse(duplicates.exists())

    def test_same_registration_seed_rebuilds_same_selection(self):
        self.write_fixture(self.known_city_events())
        self.seed_events(seed=29)

        call_command(
            'seed_registrations', seed=29, clear=True, stdout=StringIO()
        )
        first_fingerprint = self.registration_fingerprint()
        call_command(
            'seed_registrations', seed=29, clear=True, stdout=StringIO()
        )

        self.assertEqual(self.registration_fingerprint(), first_fingerprint)

    def test_known_homonyms_resolve_to_explicit_countries(self):
        self.write_fixture(self.known_city_events())

        self.seed_events()

        expected = {
            'data-belgrade': ('RS', 792680),
            'data-bergen': ('NO', 3161732),
            'data-breda': ('NL', 2758401),
            'data-essen': ('DE', 2928810),
            'data-hove': ('GB', 2646504),
        }
        actual = {
            event.slug: (event.country.code2, event.city.geoname_id)
            for event in Event.objects.select_related('country', 'city')
            if event.slug in expected
        }
        self.assertEqual(actual, expected)

    def test_brest_fixtures_resolve_to_distinct_cities(self):
        self.write_fixture(self.known_city_events())

        self.seed_events()

        belarus = Event.objects.get(slug='data-brest-by')
        france = Event.objects.get(slug='data-brest-fr')
        self.assertEqual((belarus.country.code2, belarus.city.geoname_id), ('BY', 629634))
        self.assertEqual((france.country.code2, france.city.geoname_id), ('FR', 3030300))
        self.assertNotEqual(belarus.city_id, france.city_id)

    def test_ambiguous_and_missing_cities_raise_clear_errors(self):
        City.objects.create(
            name='Twin City',
            name_ascii='Twin City',
            country=self.countries['RS'],
            geoname_id=900001,
        )
        City.objects.create(
            name='Twin City',
            name_ascii='Twin City',
            country=self.countries['RS'],
            geoname_id=900002,
        )
        ambiguous = self.event_data(
            'ambiguous-city', 'Twin City', 'RS', 900001
        )
        ambiguous.pop('city_geoname_id')
        self.write_fixture([ambiguous], 'ambiguous.json')
        missing = self.event_data(
            'missing-city', 'Missing City', 'RS', 999999
        )
        self.write_fixture([missing], 'missing.json')

        with self.assertRaisesRegex(CommandError, 'ambiguous'):
            self.seed_events('ambiguous.json')
        with self.assertRaisesRegex(CommandError, 'not found'):
            self.seed_events('missing.json')

    def test_duplicate_fixture_identity_raises_command_error(self):
        event = self.known_city_events()[0]
        duplicate = {**event, 'title': 'Different title, same identity'}
        self.write_fixture([event, duplicate])

        with self.assertRaisesRegex(CommandError, 'duplicate stable slug'):
            self.seed_events()

        self.assertFalse(Event.objects.exists())

    def test_seed_users_keeps_allauth_email_integration(self):
        call_command('seed_users', stdout=StringIO())
        user = Player.objects.get(username='rogal_dorn')
        wrong_city = City.objects.get(geoname_id=2802359)
        user.country = wrong_city.country
        user.region = wrong_city.region
        user.city = wrong_city
        user.save(update_fields=['country', 'region', 'city'])

        call_command('seed_users', stdout=StringIO())
        user.refresh_from_db()

        addresses = EmailAddress.objects.filter(user=user)
        self.assertEqual(addresses.count(), 1)
        address = addresses.get()
        self.assertEqual(address.email, user.email)
        self.assertTrue(address.primary)
        self.assertTrue(address.verified)
        self.assertEqual(user.country.code2, 'MT')
        self.assertEqual(user.city.geoname_id, 2562305)
