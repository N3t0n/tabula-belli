from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import Client, TestCase, override_settings
from django.urls import reverse


class ObservabilityHttpTest(TestCase):
    def assert_safe_error_response(self, response, internal_detail):
        body = response.content.decode()
        self.assertNotIn(settings.SECRET_KEY, body)
        self.assertNotIn('Traceback', body)
        self.assertNotIn(internal_detail, body)

    def test_logging_uses_configurable_stderr_handler(self):
        logging_config = settings.LOGGING

        self.assertEqual(logging_config['root']['level'], settings.LOG_LEVEL)
        self.assertEqual(
            logging_config['handlers']['console']['stream'],
            'ext://sys.stderr',
        )
        self.assertEqual(logging_config['loggers']['django.request']['level'], 'ERROR')

    def test_health_is_stable_and_does_not_query_demo_data(self):
        with self.assertNumQueries(0):
            response = self.client.get(reverse('health'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    @override_settings(DEBUG=False)
    def test_custom_404_does_not_expose_internal_details(self):
        response = self.client.get('/missing-obs-001-page/')

        self.assertContains(response, 'Page not found', status_code=404)
        self.assert_safe_error_response(response, 'missing-obs-001-page')

    @override_settings(DEBUG=False)
    def test_custom_403_does_not_expose_permission_detail(self):
        internal_detail = 'private authorization policy detail'

        with patch(
            'apps.pages.views.HomeView.dispatch',
            side_effect=PermissionDenied(internal_detail),
        ):
            response = self.client.get('/')

        self.assertContains(response, 'Access denied', status_code=403)
        self.assert_safe_error_response(response, internal_detail)

    @override_settings(DEBUG=False)
    def test_custom_500_does_not_expose_exception_or_traceback(self):
        internal_detail = 'private controlled failure detail'
        client = Client(raise_request_exception=False)

        with self.assertLogs('django.request', level='ERROR'):
            with patch(
                'apps.pages.views.HomeView.dispatch',
                side_effect=RuntimeError(internal_detail),
            ):
                response = client.get('/')

        self.assertContains(response, 'Something went wrong', status_code=500)
        self.assert_safe_error_response(response, internal_detail)

    @override_settings(CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'},
    })
    def test_location_database_failure_is_logged_and_returns_503(self):
        internal_detail = 'private database failure detail'

        with self.assertLogs('apps.locations.views', level='ERROR'):
            with patch(
                'apps.locations.views.Country.objects.all',
                side_effect=OperationalError(internal_detail),
            ):
                response = self.client.get(reverse('locations:get_countries'))

        self.assertEqual(response.status_code, 503)
        self.assertContains(response, 'Error loading locations', status_code=503)
        self.assert_safe_error_response(response, internal_detail)


class ObservableCommandFailureTest(TestCase):
    def test_seed_games_operational_failure_raises_command_error(self):
        with self.assertLogs(
            'apps.games.management.commands.seed_games',
            level='ERROR',
        ):
            with patch(
                'apps.games.management.commands.seed_games.Command._load_games',
                side_effect=OperationalError('private database detail'),
            ):
                with self.assertRaisesMessage(
                    CommandError,
                    'Check fixture access and database availability',
                ):
                    call_command('seed_games', stdout=StringIO(), stderr=StringIO())

    def test_load_cities_operational_failure_raises_command_error(self):
        with self.assertLogs(
            'apps.locations.management.commands.load_cities',
            level='ERROR',
        ):
            with patch(
                'apps.locations.management.commands.load_cities.Command.load_countries',
                side_effect=OSError('private source detail'),
            ):
                with self.assertRaisesMessage(
                    CommandError,
                    'Check source availability, file format, and database access',
                ):
                    call_command('load_cities', stdout=StringIO(), stderr=StringIO())
