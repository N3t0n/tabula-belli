from io import StringIO

from cities_light.models import City, Country
from django.core.management import call_command
from django.test import TestCase

from apps.players.models import Player


class SeedUsersCommandTest(TestCase):
    def test_default_seed_does_not_create_predictable_superuser(self):
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
        City.objects.create(
            name='Madrid',
            name_ascii='Madrid',
            slug='madrid',
            geoname_id=3117735,
            display_name='Madrid, Spain',
            country=country,
        )
        malta = Country.objects.create(
            name='Malta',
            name_ascii='Malta',
            slug='malta',
            geoname_id=2562770,
            code2='MT',
            code3='MLT',
            continent='EU',
            tld='.mt',
            phone='356',
        )
        City.objects.create(
            name='Valletta',
            name_ascii='Valletta',
            slug='valletta',
            geoname_id=2562305,
            display_name='Valletta, Malta',
            country=malta,
        )

        call_command('seed_users', stdout=StringIO())

        demo_player = Player.objects.get(username='rogal_dorn')
        self.assertFalse(demo_player.is_staff)
        self.assertFalse(demo_player.is_superuser)
        self.assertFalse(Player.objects.filter(username='admin').exists())
        self.assertFalse(Player.objects.filter(is_superuser=True).exists())
