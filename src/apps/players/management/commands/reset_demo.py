import logging
from io import StringIO

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from apps.accounts.demo import is_public_demo_user
from apps.events.management.commands.seed_events import (
    Command as SeedEventsCommand,
)
from apps.events.models import Event, EventRegistration
from apps.games.management.commands.seed_games import Command as SeedGamesCommand
from apps.games.models import Game
from apps.players.management.commands.seed_users import Command as SeedUsersCommand
from apps.players.models import Player
from cities_light.models import City
from config.demo_maintenance import demo_reset_lock

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Destructively rebuild the disposable demo dataset'

    RANDOM_SEED = 20250809
    EVENT_FIXTURE = 'events.json'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm the destructive demo reset',
        )

    def handle(self, *args, **options):
        config = self._validate_configuration(options['confirm'])
        seed_users = SeedUsersCommand.get_seed_users()
        events_data = self._validate_seed_inputs(seed_users)
        base_date = timezone.localdate()
        current_step = 'initialization'

        try:
            with demo_reset_lock(), transaction.atomic():
                current_step = 'deleting events and registrations'
                Event.objects.all().delete()

                current_step = 'deleting users'
                Player.objects.all().delete()

                current_step = 'deleting games'
                Game.objects.all().delete()

                current_step = 'seeding games'
                call_command('seed_games', stdout=StringIO())

                current_step = 'seeding users'
                call_command('seed_users', stdout=StringIO())
                seed_players = self._verify_seed_users(seed_users)

                current_step = 'seeding events'
                call_command(
                    'seed_events',
                    seed=self.RANDOM_SEED,
                    base_date=base_date,
                    stdout=StringIO(),
                )

                current_step = 'seeding registrations'
                call_command(
                    'seed_registrations',
                    seed=self.RANDOM_SEED,
                    stdout=StringIO(),
                )

                current_step = 'creating private admin'
                admin = self._create_admin(config)

                current_step = 'final verification'
                result = self._verify_final_state(
                    seed_users,
                    seed_players,
                    events_data,
                    admin,
                )
        except CommandError:
            raise
        except Exception as error:
            logger.exception('Demo reset failed during %s', current_step)
            raise CommandError(
                f'Demo reset failed during {current_step}; all changes rolled back.'
            ) from error

        self.stdout.write(self.style.SUCCESS('Demo reset completed.'))
        self.stdout.write(f'Games: {result["games"]}')
        self.stdout.write(f'Seed users: {result["seed_users"]}')
        self.stdout.write(f'Events: {result["events"]}')
        self.stdout.write(f'Registrations: {result["registrations"]}')
        self.stdout.write(
            f'Public demo: {settings.PUBLIC_DEMO_USERNAME}'
        )
        self.stdout.write('Admin: configured')
        self.stdout.write(f'Base date: {base_date.isoformat()}')

    @staticmethod
    def _required_setting(name):
        value = getattr(settings, name, '')
        if not isinstance(value, str) or not value.strip():
            raise CommandError(f'{name} must be configured before demo reset.')
        return value.strip()

    def _validate_configuration(self, confirmed):
        if not settings.DEMO_RESET_ALLOWED:
            raise CommandError(
                'Demo reset is disabled. Set DEMO_RESET_ALLOWED=True explicitly.'
            )
        if not confirmed:
            raise CommandError('Demo reset requires the explicit --confirm flag.')
        if connection.vendor != 'postgresql':
            raise CommandError('Demo reset supports PostgreSQL only.')

        expected_database = self._required_setting('DEMO_RESET_DATABASE_NAME')
        actual_database = str(connection.settings_dict['NAME'])
        if actual_database != expected_database:
            raise CommandError(
                'Connected database does not match DEMO_RESET_DATABASE_NAME; '
                'reset aborted.'
            )

        admin_username = self._required_setting('DEMO_ADMIN_USERNAME')
        admin_email = self._required_setting('DEMO_ADMIN_EMAIL').lower()
        admin_password = self._required_setting('DEMO_ADMIN_PASSWORD')

        seed_users = SeedUsersCommand.get_seed_users()
        seed_usernames = {user['username'] for user in seed_users}
        seed_emails = {user['email'].lower() for user in seed_users}
        if settings.PUBLIC_DEMO_USERNAME not in seed_usernames:
            raise CommandError(
                'PUBLIC_DEMO_USERNAME must identify one of the 18 seed users.'
            )
        if admin_username in seed_usernames:
            raise CommandError('DEMO_ADMIN_USERNAME must not be a seed username.')
        if admin_username == settings.PUBLIC_DEMO_USERNAME:
            raise CommandError(
                'DEMO_ADMIN_USERNAME must not be PUBLIC_DEMO_USERNAME.'
            )
        if admin_email in seed_emails:
            raise CommandError('DEMO_ADMIN_EMAIL must not be a seed email.')

        try:
            validate_email(admin_email)
            candidate = Player(username=admin_username, email=admin_email)
            validate_password(admin_password, user=candidate)
        except ValidationError as error:
            raise CommandError(
                'Demo admin credentials do not satisfy validation requirements.'
            ) from error

        return {
            'admin_username': admin_username,
            'admin_email': admin_email,
            'admin_password': admin_password,
        }

    def _validate_seed_inputs(self, seed_users):
        if len(seed_users) != 18:
            raise CommandError('seed_users must define exactly 18 demo users.')

        missing_locations = []
        for user in seed_users:
            geoname_id, city_name, country_code = user['location']
            if not City.objects.filter(
                geoname_id=geoname_id,
                country__code2=country_code,
            ).exists():
                missing_locations.append(
                    f'{city_name}, {country_code} (GeoNames ID {geoname_id})'
                )

        seed_events = SeedEventsCommand()
        fixture_path = seed_events._fixture_path(self.EVENT_FIXTURE)
        events_data = seed_events._load_fixture(fixture_path)
        for index, data in enumerate(events_data, start=1):
            missing = sorted(seed_events.REQUIRED_FIELDS - data.keys())
            if missing:
                raise CommandError(
                    f'Event {index}: missing required fields: {", ".join(missing)}'
                )
            try:
                seed_events._find_city(data, index)
            except CommandError as error:
                missing_locations.append(str(error))

        if missing_locations:
            preview = '; '.join(missing_locations[:5])
            extra = len(missing_locations) - 5
            if extra > 0:
                preview += f'; and {extra} more'
            raise CommandError(
                'Required demo Locations are missing or invalid. Run the initial '
                f'load_cities setup first. Details: {preview}'
            )

        self._validate_game_fixtures(events_data)
        return events_data

    @staticmethod
    def _validate_game_fixtures(events_data):
        seed_games = SeedGamesCommand()
        seed_games.stdout = StringIO()
        seed_games.fixtures_dir = (settings.BASE_DIR.parent / 'fixtures').resolve()
        games_data = []
        for category, filename in seed_games.CATEGORY_FILES.items():
            file_path = seed_games.fixtures_dir / filename
            if not file_path.is_file():
                raise CommandError(f'Required fixture file not found: {filename}')
            games_data.extend(seed_games._parse_csv(file_path, category))
        seed_games._validate_games_data(games_data)

        game_names = {game['name'].casefold() for game in games_data}
        missing_games = sorted({
            event['game']
            for event in events_data
            if event['game'].casefold() not in game_names
        })
        if missing_games:
            raise CommandError(
                'Event fixtures reference games absent from game fixtures: '
                + ', '.join(missing_games[:5])
            )

    @staticmethod
    def _verify_seed_users(seed_users):
        usernames = [user['username'] for user in seed_users]
        players = list(Player.objects.filter(username__in=usernames))
        if len(players) != 18:
            raise CommandError('seed_users did not create all 18 demo users.')

        addresses = EmailAddress.objects.filter(user__username__in=usernames)
        duplicate_users = addresses.values('user_id').annotate(
            total=Count('id')
        ).filter(total__gt=1)
        if (
            addresses.count() != 18
            or addresses.filter(primary=True, verified=True).count() != 18
            or duplicate_users.exists()
        ):
            raise CommandError(
                'Seed user EmailAddress state is not exactly primary and verified.'
            )

        demo = next(
            player for player in players
            if player.username == settings.PUBLIC_DEMO_USERNAME
        )
        demo_seed = next(
            user for user in seed_users
            if user['username'] == settings.PUBLIC_DEMO_USERNAME
        )
        if (
            demo.is_staff
            or demo.is_superuser
            or not demo.check_password(demo_seed['password'])
            or not is_public_demo_user(demo)
        ):
            raise CommandError('Public demo account failed AUTH-DEMO verification.')
        if any(
            player.has_usable_password()
            for player in players
            if player.username != settings.PUBLIC_DEMO_USERNAME
        ):
            raise CommandError(
                'A non-public seed user has a usable password.'
            )
        return players

    @staticmethod
    def _create_admin(config):
        admin = Player.objects.create_superuser(
            username=config['admin_username'],
            email=config['admin_email'],
            password=config['admin_password'],
        )
        EmailAddress.objects.create(
            user=admin,
            email=admin.email,
            primary=True,
            verified=True,
        )
        return admin

    @staticmethod
    def _verify_final_state(seed_users, seed_players, events_data, admin):
        expected_usernames = {user['username'] for user in seed_users}
        actual_usernames = {player.username for player in seed_players}
        if actual_usernames != expected_usernames:
            raise CommandError('Final seed user identities do not match the seed.')
        if Player.objects.count() != 19:
            raise CommandError('Final demo must contain 18 seed users and one admin.')

        admin_address = EmailAddress.objects.filter(
            user=admin,
            primary=True,
            verified=True,
        )
        if (
            not admin.is_staff
            or not admin.is_superuser
            or admin_address.count() != 1
            or admin.organized_events.exists()
            or admin.event_registrations.exists()
        ):
            raise CommandError('Private demo admin failed final verification.')

        if Event.objects.count() != len(events_data):
            raise CommandError('Final event count does not match events fixture.')
        if EventRegistration.objects.exclude(
            player__username__in=expected_usernames
        ).exists():
            raise CommandError('Non-seed user found in demo registrations.')

        return {
            'games': Game.objects.count(),
            'seed_users': len(expected_usernames),
            'events': Event.objects.count(),
            'registrations': EventRegistration.objects.count(),
        }
