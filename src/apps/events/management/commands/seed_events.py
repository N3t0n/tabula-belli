import json
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.events.models import Event
from apps.events.services import derive_initial_status
from apps.games.models import Game
from apps.players.models import Player
from cities_light.models import City


class Command(BaseCommand):
    help = 'Load deterministic demo events from JSON fixtures'

    DEFAULT_RANDOM_SEED = 20250809
    REQUIRED_FIELDS = {
        'title',
        'slug',
        'event_type',
        'description',
        'start_offset_days',
        'start_time_hour',
        'start_time_minute',
        'end_offset_days',
        'end_time_hour',
        'end_time_minute',
        'registration_opens_offset_days',
        'registration_opens_time_hour',
        'registration_opens_time_minute',
        'registration_closes_offset_days',
        'registration_closes_time_hour',
        'registration_closes_time_minute',
        'capacity',
        'price',
        'location_name',
        'location_address',
        'city',
        'country_code',
        'game',
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default='events.json',
            help='JSON fixture filename inside the fixtures directory',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=self.DEFAULT_RANDOM_SEED,
            help='Reproducible organizer selection seed',
        )
        parser.add_argument(
            '--base-date',
            type=self.parse_base_date,
            default=None,
            help='ISO date used for fixture offsets (default: local today)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Explicitly delete all events and registrations before seeding',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate and preview without database writes',
        )

    @staticmethod
    def parse_base_date(value):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise CommandError(
                f'Invalid --base-date {value!r}; expected YYYY-MM-DD'
            ) from error

    @staticmethod
    def fixture_datetime(base_date, offset_days, hour, minute):
        event_date = base_date + timedelta(days=int(offset_days))
        event_time = time(hour=int(hour), minute=int(minute))
        return timezone.make_aware(datetime.combine(event_date, event_time))

    def handle(self, *args, **options):
        fixture_path = self._fixture_path(options['file'])
        events_data = self._load_fixture(fixture_path)
        organizers = list(Player.objects.order_by('username', 'pk'))
        if not organizers:
            raise CommandError('No players found. Run seed_users first.')

        base_date = options['base_date'] or timezone.localdate()
        randomizer = random.Random(options['seed'])
        prepared_events = self._prepare_events(
            events_data,
            organizers,
            randomizer,
            base_date,
        )

        self.stdout.write(
            f'Loading {len(prepared_events)} events from {fixture_path.name} '
            f'(seed={options["seed"]}, base_date={base_date.isoformat()})'
        )

        if options['dry_run']:
            created = sum(
                not Event.objects.filter(slug=slug).exists()
                for slug, _defaults in prepared_events
            )
            self.stdout.write('DRY RUN mode: no database changes')
            self.stdout.write(
                f'Would create {created}, update {len(prepared_events) - created}'
            )
            return

        created = 0
        updated = 0
        with transaction.atomic():
            if options['clear']:
                deleted = Event.objects.all().delete()[0]
                self.stdout.write(
                    f'Explicit --clear removed {deleted} events/related rows'
                )

            for slug, defaults in prepared_events:
                _event, is_new = Event.objects.update_or_create(
                    slug=slug,
                    defaults=defaults,
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Created {created}, updated {updated}'
        ))
        self.stdout.write(f'Total events: {Event.objects.count()}')

    def _fixture_path(self, filename):
        fixtures_dir = (settings.BASE_DIR.parent / 'fixtures').resolve()
        fixture_path = (fixtures_dir / filename).resolve()
        if fixture_path.parent != fixtures_dir:
            raise CommandError('Event fixture must be inside the fixtures directory')
        if not fixture_path.is_file():
            raise CommandError(f'Event fixture not found: {fixture_path}')
        return fixture_path

    @staticmethod
    def _load_fixture(fixture_path):
        try:
            with fixture_path.open('r', encoding='utf-8') as fixture_file:
                events_data = json.load(fixture_file)
        except (OSError, json.JSONDecodeError) as error:
            raise CommandError(
                f'Cannot load event fixture {fixture_path}: {error}'
            ) from error

        if not isinstance(events_data, list) or not events_data:
            raise CommandError('Event fixture must be a non-empty JSON list')
        return events_data

    def _prepare_events(self, events_data, organizers, randomizer, base_date):
        prepared_events = []
        seen_slugs = set()

        for index, data in enumerate(events_data, start=1):
            if not isinstance(data, dict):
                raise CommandError(f'Event {index}: expected a JSON object')

            missing = sorted(self.REQUIRED_FIELDS - data.keys())
            if missing:
                raise CommandError(
                    f'Event {index}: missing required fields: {", ".join(missing)}'
                )

            slug = data['slug']
            if not isinstance(slug, str) or not slug or len(slug) > 200:
                raise CommandError(f'Event {index}: invalid stable slug {slug!r}')
            if slug in seen_slugs:
                raise CommandError(f'Event {index}: duplicate stable slug {slug!r}')
            seen_slugs.add(slug)

            city = self._find_city(data, index)
            game = self._find_game(data['game'], index)

            try:
                start_at = self.fixture_datetime(
                    base_date,
                    data['start_offset_days'],
                    data['start_time_hour'],
                    data['start_time_minute'],
                )
                end_at = self.fixture_datetime(
                    base_date,
                    data['end_offset_days'],
                    data['end_time_hour'],
                    data['end_time_minute'],
                )
                registration_opens_at = self.fixture_datetime(
                    base_date,
                    data['registration_opens_offset_days'],
                    data['registration_opens_time_hour'],
                    data['registration_opens_time_minute'],
                )
                registration_closes_at = self.fixture_datetime(
                    base_date,
                    data['registration_closes_offset_days'],
                    data['registration_closes_time_hour'],
                    data['registration_closes_time_minute'],
                )
                capacity = int(data['capacity'])
                price = Decimal(str(data['price']))
            except (TypeError, ValueError, InvalidOperation) as error:
                raise CommandError(
                    f'Event {index} ({slug}): invalid fixture value: {error}'
                ) from error

            if end_at <= start_at:
                raise CommandError(f'Event {index} ({slug}): end must follow start')
            if capacity < 1 or capacity > 10000:
                raise CommandError(
                    f'Event {index} ({slug}): capacity must be 1-10000'
                )

            organizer = randomizer.choice(organizers)
            prepared_events.append((slug, {
                'title': data['title'],
                'event_type': data['event_type'],
                'status': derive_initial_status(end_at),
                'description': data['description'],
                'start_at': start_at,
                'end_at': end_at,
                'capacity': capacity,
                'price': price,
                'registration_opens_at': registration_opens_at,
                'registration_closes_at': registration_closes_at,
                'country': city.country,
                'region': city.region,
                'city': city,
                'location_name': data['location_name'],
                'location_address': data['location_address'],
                'game': game,
                'organizer': organizer,
                'contact_email': organizer.email,
            }))

        return prepared_events

    @staticmethod
    def _find_city(data, index):
        country_code = str(data['country_code']).upper()
        city_name = data['city']
        geoname_id = data.get('city_geoname_id')

        cities = City.objects.select_related('country', 'region').filter(
            country__code2=country_code,
        )
        if geoname_id is not None:
            cities = cities.filter(geoname_id=geoname_id)
        else:
            cities = cities.filter(
                Q(name__iexact=city_name) | Q(name_ascii__iexact=city_name)
            )

        matches = list(cities[:2])
        if not matches:
            identity = f'GeoNames ID {geoname_id}' if geoname_id else city_name
            raise CommandError(
                f'Event {index}: city {identity!r} not found in {country_code}'
            )
        if len(matches) > 1:
            raise CommandError(
                f'Event {index}: city {city_name!r} is ambiguous in '
                f'{country_code}; add city_geoname_id'
            )
        return matches[0]

    @staticmethod
    def _find_game(game_name, index):
        try:
            return Game.objects.get(name__iexact=game_name)
        except Game.DoesNotExist as error:
            raise CommandError(
                f'Event {index}: game {game_name!r} not found; run seed_games first'
            ) from error
        except Game.MultipleObjectsReturned as error:
            raise CommandError(
                f'Event {index}: game reference {game_name!r} is ambiguous'
            ) from error
