import csv
import logging
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction
from django.utils.text import slugify

from apps.games.models import Game

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Load official games from CSV fixtures'

    CATEGORY_FILES = {
        'TCG': 'games_tcgs.csv',
        'TTRPG': 'games_ttrpgs.csv',
        'WARGAME': 'games_wargames.csv',
    }

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Delete existing games')
        parser.add_argument('--dry-run', action='store_true',
                            help='Preview without changes')
        parser.add_argument(
            '--category', choices=['TCG', 'TTRPG', 'WARGAME'], help='Load specific category')

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.reset = options['reset']
        self.target_category = options.get('category')
        self.fixtures_dir = (settings.BASE_DIR.parent / 'fixtures').resolve()

        if not self.fixtures_dir.exists():
            raise CommandError(
                f"Fixtures directory not found: {self.fixtures_dir}")

        official_count = Game.objects.filter(is_official=True).count()

        if official_count == 0:
            self.stdout.write("No games found. Loading...")
        elif not self.reset:
            self.stdout.write(
                f"{official_count} games already loaded. Use --reset to reload")
            return

        try:
            self._load_games()
        except CommandError:
            raise
        except (OSError, DatabaseError) as error:
            logger.exception('Game seed failed during fixture or database access')
            raise CommandError(
                'Failed to load games. Check fixture access and database availability.'
            ) from error

    def _load_games(self):
        if self.target_category:
            files_to_load = {
                self.target_category: self.CATEGORY_FILES[self.target_category]}
        else:
            files_to_load = self.CATEGORY_FILES

        games_data = []
        for category, filename in files_to_load.items():
            file_path = self.fixtures_dir / filename

            if not file_path.exists():
                raise CommandError(f"Required fixture file not found: {filename}")

            games_from_file = self._parse_csv(file_path, category)
            games_data.extend(games_from_file)
            self.stdout.write(
                f"Parsed {len(games_from_file)} games from {filename}")

        if not games_data:
            raise CommandError('No games found in the required CSV fixtures')

        self._validate_games_data(games_data)

        if self.dry_run:
            self._show_preview(games_data)
            return

        if self.reset:
            self._reset_official_games()

        self._load_into_database(games_data)

    def _parse_csv(self, file_path, category):
        games = []

        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                if 'name' not in reader.fieldnames:
                    raise CommandError(
                        f"CSV must have 'name' column: {file_path}")

                for row_num, row in enumerate(reader, start=2):
                    if not row.get('name', '').strip():
                        continue

                    name = row['name'].strip()
                    description = row.get('description', '').strip()

                    if len(name) > 150:
                        raise CommandError(
                            f"{file_path}:{row_num} - Name too long (max 150 chars): {name[:50]}..."
                        )

                    if len(description) > 5000:
                        raise CommandError(
                            f"{file_path}:{row_num} - Description too long (max 5000 chars)"
                        )

                    slug = slugify(name)
                    if not slug:
                        raise CommandError(
                            f"{file_path}:{row_num} - Cannot generate slug from name: {name}"
                        )

                    games.append({
                        'name': name,
                        'category': category,
                        'slug': slug,
                        'description': description,
                        'source_file': file_path.name,
                        'source_line': row_num,
                    })

        except UnicodeDecodeError:
            raise CommandError(
                f"File encoding error: {file_path}\n"
                f"Ensure file is saved as UTF-8 with BOM"
            )
        except csv.Error as e:
            raise CommandError(f"CSV parsing error in {file_path}: {e}")

        return games

    def _validate_games_data(self, games_data):
        slugs = [game['slug'] for game in games_data]
        slug_counts = Counter(slugs)
        duplicates = {slug: count for slug,
                      count in slug_counts.items() if count > 1}

        if duplicates:
            error_msg = ["Duplicate slugs detected in CSV files:"]
            for slug, count in duplicates.items():
                games_with_slug = [g for g in games_data if g['slug'] == slug]
                error_msg.append(f"\n  Slug '{slug}' appears {count} times:")
                for game in games_with_slug:
                    error_msg.append(
                        f"    - {game['name']} ({game['source_file']}:{game['source_line']})")

            error_msg.append(
                "\nFix: Ensure game names are sufficiently different to generate unique slugs.")
            raise CommandError('\n'.join(error_msg))

        self.stdout.write(f"Validated {len(games_data)} games")

    def _show_preview(self, games_data):
        self.stdout.write(self.style.WARNING('DRY RUN mode'))

        by_category = {}
        for game in games_data:
            cat = game['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(game)

        for category, games in sorted(by_category.items()):
            self.stdout.write(f"{category}: {len(games)} games")

        self.stdout.write(f"Total: {len(games_data)} games would be loaded")

    def _reset_official_games(self):
        queryset = Game.objects.filter(is_official=True)

        if self.target_category:
            queryset = queryset.filter(category=self.target_category)
            msg = f"official {self.target_category} games"
        else:
            msg = "all official games"

        count = queryset.count()
        if count > 0:
            queryset.delete()
            self.stdout.write(f"Deleted {count} games")

    def _load_into_database(self, games_data):
        self.stdout.write(f"Loading {len(games_data)} games...")

        created = 0
        updated = 0

        with transaction.atomic():
            for data in games_data:
                game, is_new = Game.objects.update_or_create(
                    slug=data['slug'],
                    defaults={
                        'name': data['name'],
                        'category': data['category'],
                        'description': data['description'],
                        'is_official': True,
                        'created_by': None,
                    }
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(f"Created {created}, updated {updated}")
        self.stdout.write(
            f"Total: {Game.objects.filter(is_official=True).count()}")
