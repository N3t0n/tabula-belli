import random

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.events.models import Event, EventRegistration
from apps.players.models import Player


class Command(BaseCommand):
    help = 'Create deterministic demo registrations for open events'

    DEFAULT_RANDOM_SEED = 20250809

    def add_arguments(self, parser):
        parser.add_argument(
            '--seed',
            type=int,
            default=self.DEFAULT_RANDOM_SEED,
            help='Reproducible registration selection seed',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Explicitly delete all registrations before seeding',
        )

    def handle(self, *args, **options):
        players = list(Player.objects.order_by('username', 'pk'))
        if not players:
            raise CommandError('No players found. Run seed_users first.')

        now = timezone.now()
        events_open = [
            event
            for event in Event.objects.order_by('slug', 'pk')
            if event.status == Event.Status.ACTIVE
            and now < event.start_at
            and (
                event.registration_opens_at is None
                or now >= event.registration_opens_at
            )
            and (
                event.registration_closes_at is None
                or now < event.registration_closes_at
            )
        ]
        self.stdout.write(
            f'Found {len(events_open)} events with OPEN registration '
            f'(seed={options["seed"]})'
        )

        randomizer = random.Random(options['seed'])
        plan = []
        for event in events_open:
            if randomizer.random() <= 0.3:
                continue

            num_registrations = randomizer.randint(
                1,
                min(5, event.capacity, len(players)),
            )
            for player in randomizer.sample(players, num_registrations):
                plan.append((event, player))

        created = 0
        skipped = 0
        with transaction.atomic():
            if options['clear']:
                deleted = EventRegistration.objects.all().delete()[0]
                self.stdout.write(
                    f'Explicit --clear removed {deleted} registrations'
                )

            for event, player in plan:
                if EventRegistration.objects.filter(
                    event=event,
                    player=player,
                    status=EventRegistration.Status.CONFIRMED,
                ).exists():
                    skipped += 1
                    continue

                try:
                    EventRegistration.register(event=event, player=player)
                except ValidationError as error:
                    raise CommandError(
                        f'Cannot seed registration for {player.username!r} '
                        f'in {event.slug!r}: {error}'
                    ) from error
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Created {created}, skipped {skipped} existing registrations'
        ))
        self.stdout.write(
            f'Total registrations: {EventRegistration.objects.count()}'
        )
