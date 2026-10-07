import csv
import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from allauth.account.models import EmailAddress
from cities_light.models import City, Country
from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.events.models import Event, EventRegistration
from apps.games.models import Game
from apps.players.management.commands.reset_demo import Command as ResetDemoCommand
from apps.players.management.commands.seed_users import Command as SeedUsersCommand
from apps.players.models import Player


class DemoResetCommandTest(TestCase):
    admin_username = 'private_demo_admin'
    admin_email = 'private-admin@example.com'
    admin_password = 'J7!vQ2#nL9@xR4'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_dir = TemporaryDirectory()
        cls.project_root = Path(cls.temp_dir.name)
        cls.fixtures_dir = cls.project_root / 'fixtures'
        cls.fixtures_dir.mkdir()
        cls._write_game_fixtures()
        cls._write_event_fixture()

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        seed_users = SeedUsersCommand.get_seed_users()
        countries = {}
        for user in seed_users:
            geoname_id, city_name, country_code = user['location']
            country = countries.get(country_code)
            if country is None:
                country = Country.objects.create(
                    name=f'{country_code} Demo Country',
                    code2=country_code,
                    code3=f'{country_code}X',
                )
                countries[country_code] = country
            City.objects.create(
                name=city_name,
                name_ascii=city_name,
                country=country,
                geoname_id=geoname_id,
            )

        cls.visitor = Player.objects.create_user(
            username='visitor-before-reset',
            email='visitor-before-reset@example.com',
            password='VisitorPass123!',
        )
        cls.visitor_game = Game.objects.create(
            name='Visitor Created Game',
            slug='visitor-created-game',
            category=Game.Category.TCG,
            created_by=cls.visitor,
        )
        city = City.objects.get(geoname_id=2761369)
        now = timezone.now()
        cls.visitor_event = Event.objects.create(
            title='Visitor Event',
            slug='visitor-event-before-reset',
            organizer=cls.visitor,
            game=cls.visitor_game,
            country=city.country,
            region=city.region,
            city=city,
            contact_email=cls.visitor.email,
            start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=2, hours=2),
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=1),
            capacity=5,
        )
        EventRegistration.objects.create(
            event=cls.visitor_event,
            player=cls.visitor,
        )

    @classmethod
    def _write_game_fixtures(cls):
        fixtures = {
            'games_tcgs.csv': 'Demo TCG',
            'games_ttrpgs.csv': 'Demo TTRPG',
            'games_wargames.csv': 'Demo Wargame',
        }
        for filename, game_name in fixtures.items():
            with (cls.fixtures_dir / filename).open(
                'w', encoding='utf-8', newline=''
            ) as fixture_file:
                writer = csv.DictWriter(
                    fixture_file, fieldnames=['name', 'description']
                )
                writer.writeheader()
                writer.writerow({
                    'name': game_name,
                    'description': f'{game_name} fixture',
                })

    @classmethod
    def _write_event_fixture(cls):
        event = {
            'title': 'Reset Demo Event',
            'slug': 'reset-demo-event',
            'event_type': Event.EventType.CASUAL,
            'description': 'Reset demo test event',
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
            'price': '0.00',
            'location_name': 'Reset Demo Venue',
            'location_address': 'Reset Demo Address',
            'city': 'Vienna',
            'country_code': 'AT',
            'city_geoname_id': 2761369,
            'game': 'Demo TCG',
        }
        (cls.fixtures_dir / 'events.json').write_text(
            json.dumps([event]), encoding='utf-8'
        )

    def reset_settings(self, **overrides):
        values = {
            'BASE_DIR': self.project_root / 'src',
            'DEMO_RESET_ALLOWED': True,
            'DEMO_RESET_DATABASE_NAME': connection.settings_dict['NAME'],
            'DEMO_ADMIN_USERNAME': self.admin_username,
            'DEMO_ADMIN_EMAIL': self.admin_email,
            'DEMO_ADMIN_PASSWORD': self.admin_password,
            'PUBLIC_DEMO_USERNAME': 'horus_lupercal',
            'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
        }
        values.update(overrides)
        return self.settings(**values)

    @staticmethod
    def data_fingerprint():
        return {
            'players': list(Player.objects.order_by('username').values_list(
                'username', 'email', 'is_staff', 'is_superuser'
            )),
            'games': list(Game.objects.order_by('slug').values_list(
                'slug', 'name', 'is_official'
            )),
            'events': list(Event.objects.order_by('slug').values_list(
                'slug', 'organizer__username', 'game__slug', 'start_at'
            )),
            'registrations': list(EventRegistration.objects.order_by(
                'event__slug', 'player__username'
            ).values_list('event__slug', 'player__username', 'status')),
        }

    def call_reset(self, *, confirm=True, **settings_overrides):
        output = StringIO()
        with self.reset_settings(**settings_overrides):
            call_command('reset_demo', confirm=confirm, stdout=output)
        return output.getvalue()

    def assert_original_data_untouched(self, fingerprint):
        self.assertEqual(self.data_fingerprint(), fingerprint)
        self.assertTrue(
            Player.objects.filter(username='visitor-before-reset').exists()
        )
        self.assertTrue(
            Event.objects.filter(slug='visitor-event-before-reset').exists()
        )

    def test_disabled_reset_aborts_without_changes(self):
        before = self.data_fingerprint()

        with self.assertRaisesRegex(CommandError, 'disabled'):
            self.call_reset(DEMO_RESET_ALLOWED=False)

        self.assert_original_data_untouched(before)

    def test_missing_confirmation_aborts_without_changes(self):
        before = self.data_fingerprint()

        with self.assertRaisesRegex(CommandError, '--confirm'):
            self.call_reset(confirm=False)

        self.assert_original_data_untouched(before)

    def test_incomplete_admin_configuration_aborts_before_delete(self):
        before = self.data_fingerprint()

        with self.assertRaisesRegex(CommandError, 'DEMO_ADMIN_EMAIL'):
            self.call_reset(DEMO_ADMIN_EMAIL='')

        self.assert_original_data_untouched(before)

    def test_database_mismatch_aborts_without_changes(self):
        before = self.data_fingerprint()

        with self.assertRaisesRegex(CommandError, 'does not match'):
            self.call_reset(DEMO_RESET_DATABASE_NAME='not-this-database')

        self.assert_original_data_untouched(before)

    def test_missing_required_location_aborts_before_delete(self):
        City.objects.filter(geoname_id=2562305).delete()
        before = self.data_fingerprint()

        with self.assertRaisesRegex(CommandError, 'load_cities'):
            self.call_reset()

        self.assert_original_data_untouched(before)

    def test_complete_reset_rebuilds_demo_and_creates_admin_last(self):
        location_count = City.objects.count()
        original_create_admin = ResetDemoCommand._create_admin
        admin_creation_state = []

        def create_admin_after_seed(config):
            admin_creation_state.append({
                'events': Event.objects.count(),
                'registrations': EventRegistration.objects.count(),
                'players': Player.objects.count(),
            })
            return original_create_admin(config)

        with patch.object(
            ResetDemoCommand,
            '_create_admin',
            side_effect=create_admin_after_seed,
        ):
            output = self.call_reset()

        seed_users = SeedUsersCommand.get_seed_users()
        usernames = {user['username'] for user in seed_users}
        addresses = EmailAddress.objects.filter(user__username__in=usernames)
        demo_seed = next(
            user for user in seed_users if user['username'] == 'horus_lupercal'
        )
        private_seed_users = [
            user for user in seed_users
            if user['username'] != 'horus_lupercal'
        ]
        demo = Player.objects.get(username='horus_lupercal')
        admin = Player.objects.get(username=self.admin_username)

        self.assertFalse(
            Player.objects.filter(username='visitor-before-reset').exists()
        )
        self.assertFalse(
            Event.objects.filter(slug='visitor-event-before-reset').exists()
        )
        self.assertFalse(
            Game.objects.filter(slug='visitor-created-game').exists()
        )
        self.assertEqual(City.objects.count(), location_count)
        self.assertEqual(Player.objects.filter(username__in=usernames).count(), 18)
        self.assertEqual(addresses.count(), 18)
        self.assertEqual(
            addresses.filter(primary=True, verified=True).count(), 18
        )
        self.assertFalse(demo.is_staff)
        self.assertFalse(demo.is_superuser)
        self.assertTrue(demo.check_password(demo_seed['password']))
        self.assertIsNotNone(authenticate(
            username=demo.username,
            password=demo_seed['password'],
        ))
        for seed_user in private_seed_users:
            with self.subTest(username=seed_user['username']):
                player = Player.objects.get(username=seed_user['username'])
                self.assertFalse(player.has_usable_password())
                self.assertIsNone(authenticate(
                    username=player.username,
                    password=seed_user['password'],
                ))

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password(self.admin_password))
        self.assertTrue(EmailAddress.objects.filter(
            user=admin, primary=True, verified=True
        ).exists())
        self.assertFalse(admin.organized_events.exists())
        self.assertFalse(admin.event_registrations.exists())
        self.assertEqual(admin_creation_state, [{
            'events': 1,
            'registrations': EventRegistration.objects.count(),
            'players': 18,
        }])
        self.assertGreater(admin_creation_state[0]['registrations'], 0)
        self.assertIn('Demo reset completed.', output)
        self.assertIn('Seed users: 18', output)
        self.assertNotIn(self.admin_password, output)
        self.assertNotIn(demo_seed['password'], output)

    def test_two_consecutive_resets_produce_same_valid_state(self):
        self.call_reset()
        first = self.data_fingerprint()

        self.call_reset()
        second = self.data_fingerprint()

        self.assertEqual(second, first)
        self.assertEqual(Player.objects.count(), 19)
        self.assertEqual(Event.objects.count(), 1)
        self.assertGreater(EventRegistration.objects.count(), 0)

    def test_controlled_seed_failure_rolls_back_and_stops(self):
        before = self.data_fingerprint()
        real_call_command = call_command
        calls = []

        def fail_at_events(name, *args, **kwargs):
            calls.append(name)
            if name == 'seed_events':
                raise CommandError('controlled seed failure')
            return real_call_command(name, *args, **kwargs)

        with patch(
            'apps.players.management.commands.reset_demo.call_command',
            side_effect=fail_at_events,
        ):
            with self.assertRaisesRegex(CommandError, 'controlled seed failure'):
                self.call_reset()

        self.assertEqual(calls, ['seed_games', 'seed_users', 'seed_events'])
        self.assert_original_data_untouched(before)
