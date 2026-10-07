import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from cities_light.geonames import Geonames
from cities_light.models import Country, Region, City
from cities_light.settings import ICountry, IRegion, ICity

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Load GeoNames data (countries, regions, cities)'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int,
                            default=3000, help='Cities per batch')

    def handle(self, *args, **options):
        batch_size = options['batch_size']

        self.stdout.write("Loading GeoNames data\n")

        try:
            countries_count = self.load_countries()
            regions_count = self.load_regions_batch()
            cities_count = self.load_cities_batch(batch_size)

            self.stdout.write(
                f"\nCompleted: {countries_count} countries, {regions_count} regions, {cities_count:,} cities")

        except CommandError:
            raise
        except Exception as error:
            logger.exception('GeoNames data load failed')
            raise CommandError(
                'Failed to load GeoNames data. Check source availability, '
                'file format, and database access.'
            ) from error

    def get_source(self, local_filename, setting_key):
        cache_dir = settings.BASE_DIR / '.cities_light'
        local_path = cache_dir / local_filename
        if local_path.exists():
            return str(local_path)
        return getattr(settings, setting_key)[0]

    def load_countries(self):
        source = self.get_source(
            'countryInfo.txt', 'CITIES_LIGHT_COUNTRY_SOURCES')
        target_countries = set(settings.CITIES_LIGHT_INCLUDE_COUNTRIES)

        geonames = Geonames(source, force=True)

        created_count = 0
        for items in geonames.parse():
            # Filter: only European countries
            if items[ICountry.code2] not in target_countries:
                continue

            country, created = Country.objects.get_or_create(
                code2=items[ICountry.code2],
                defaults=dict(
                    name=items[ICountry.name],
                    code3=items[ICountry.code3],
                    continent=items[ICountry.continent],
                    tld=items[ICountry.tld] if items[ICountry.tld] else '',
                    phone=items[ICountry.phone] if items[ICountry.phone] else '',
                )
            )
            if created:
                created_count += 1

        total = Country.objects.count()
        return total

    def load_regions_batch(self):
        source = self.get_source(
            'admin1CodesASCII.txt', 'CITIES_LIGHT_REGION_SOURCES')
        target_countries = set(settings.CITIES_LIGHT_INCLUDE_COUNTRIES)
        countries_map = {c.code2: c for c in Country.objects.filter(
            code2__in=target_countries)}

        geonames = Geonames(source, force=True)

        regions_created = 0
        for items in geonames.parse():
            code_parts = items[IRegion.code].split('.')
            if len(code_parts) != 2:
                continue

            country_code = code_parts[0]
            if country_code not in target_countries:
                continue

            country = countries_map.get(country_code)
            if not country:
                continue

            region, created = Region.objects.get_or_create(
                country=country,
                geoname_code=code_parts[1],
                defaults=dict(
                    name=items[IRegion.name],
                    name_ascii=items[IRegion.asciiName],
                    geoname_id=int(items[IRegion.geonameid]
                                   ) if items[IRegion.geonameid] else None,
                )
            )

            if created:
                regions_created += 1

        total = Region.objects.count()
        return total

    def load_cities_batch(self, batch_size=3000):
        source = self.get_source('cities1000.zip', 'CITIES_LIGHT_CITY_SOURCES')
        target_countries = set(settings.CITIES_LIGHT_INCLUDE_COUNTRIES)
        countries_map = {c.code2: c for c in Country.objects.filter(
            code2__in=target_countries)}

        regions_map = {}
        for region in Region.objects.select_related('country').all():
            key = f"{region.country.code2}.{region.geoname_code}"
            regions_map[key] = region

        geonames = Geonames(source, force=True)

        cities_batch = []
        cities_processed = 0
        total_lines = 0

        for items in geonames.parse():
            total_lines += 1

            if items[ICity.featureClass] != 'P':
                continue

            country_code = items[ICity.countryCode]
            if country_code not in target_countries:
                continue
            try:
                population = int(items[ICity.population]
                                 ) if items[ICity.population] else 0
            except (ValueError, IndexError):
                population = 0

            if population < 1000:
                continue

            cities_processed += 1

            country = countries_map.get(country_code)
            if not country:
                continue

            region_key = f"{country_code}.{items[ICity.admin1Code]}"
            region = regions_map.get(region_key)

            try:
                city_data = dict(
                    geoname_id=int(items[ICity.geonameid]
                                   ) if items[ICity.geonameid] else None,
                    name=items[ICity.name],
                    name_ascii=items[ICity.asciiName] if items[ICity.asciiName] else items[ICity.name],
                    latitude=float(items[ICity.latitude]
                                   ) if items[ICity.latitude] else None,
                    longitude=float(items[ICity.longitude]
                                    ) if items[ICity.longitude] else None,
                    country=country,
                    region=region,
                    population=population,
                    feature_code=items[ICity.featureCode] if items[ICity.featureCode] else '',
                    timezone=items[ICity.timezone] if items[ICity.timezone] else '',
                )

                cities_batch.append(city_data)

                if len(cities_batch) >= batch_size:
                    self._save_cities_batch(cities_batch)
                    cities_batch = []

            except (ValueError, IndexError):
                continue

        if cities_batch:
            self._save_cities_batch(cities_batch)

        total = City.objects.count()
        return total

    def _save_cities_batch(self, cities_batch):
        geoname_ids = [c['geoname_id']
                       for c in cities_batch if c.get('geoname_id')]
        existing_ids = set(City.objects.filter(
            geoname_id__in=geoname_ids).values_list('geoname_id', flat=True))

        city_objects = []
        for city_data in cities_batch:
            geoname_id = city_data.get('geoname_id')
            if geoname_id and geoname_id not in existing_ids:
                city_objects.append(City(**city_data))

        if city_objects:
            with transaction.atomic():
                City.objects.bulk_create(city_objects, ignore_conflicts=True)

        return len(city_objects)
