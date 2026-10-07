from django.conf import settings
from django.test import SimpleTestCase


class GeoNamesSourceConfigTest(SimpleTestCase):
    def test_geonames_sources_use_https(self):
        sources = (
            settings.CITIES_LIGHT_COUNTRY_SOURCES
            + settings.CITIES_LIGHT_REGION_SOURCES
            + settings.CITIES_LIGHT_CITY_SOURCES
        )

        self.assertTrue(sources)
        for source in sources:
            with self.subTest(source=source):
                self.assertTrue(
                    source.startswith('https://download.geonames.org/')
                )
                self.assertNotIn('http://download.geonames.org/', source)
