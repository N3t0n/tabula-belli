from django.core.management.base import BaseCommand
from apps.events.services import complete_past_events


class Command(BaseCommand):
    help = 'Mark all past ACTIVE events as COMPLETED'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            from apps.events.models import Event
            from django.utils import timezone

            count = Event.objects.filter(
                status=Event.Status.ACTIVE,
                end_at__lte=timezone.now()
            ).count()

            self.stdout.write(
                self.style.WARNING(f'[DRY RUN] Would complete {count} events')
            )
        else:
            updated = complete_past_events()

            if updated > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Completed {updated} past events')
                )
            else:
                self.stdout.write('No past events to complete')
