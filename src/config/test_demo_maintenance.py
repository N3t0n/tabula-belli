from threading import Event as ThreadEvent, Thread
from unittest.mock import Mock

from django.core.management.base import CommandError
from django.db import connection, connections
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, TransactionTestCase

from apps.events.services import complete_past_events
from config.demo_maintenance import (
    APP_ACTIVITY, LOCK_NAMESPACE, RESET_INTENT,
    DemoMaintenanceMiddleware, application_access, demo_reset_lock,
)


class DemoMaintenanceTest(TransactionTestCase):
    """Real, independent PostgreSQL sessions exercise the concurrency contract."""

    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL advisory locks required')
        self.other = connection.copy(alias='maintenance-test')
        self.addCleanup(self.other.close)
        self.factory = RequestFactory()

    def other_lock(self, key, shared=False):
        function = 'pg_try_advisory_lock_shared' if shared else 'pg_try_advisory_lock'
        with self.other.cursor() as cursor:
            cursor.execute(f'SELECT {function}(%s, %s)', [LOCK_NAMESPACE, key])
            return cursor.fetchone()[0]

    def test_maintenance_blocks_get_post_and_admin_without_running_view(self):
        self.assertTrue(self.other_lock(RESET_INTENT))
        downstream = Mock(return_value=HttpResponse('normal'))
        middleware = DemoMaintenanceMiddleware(downstream)
        for method, path in [('get', '/'), ('post', '/accounts/signup/'), ('get', '/admin/')]:
            with self.subTest(method=method, path=path):
                response = middleware(getattr(self.factory, method)(path))
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response['Retry-After'], '60')
                self.assertEqual(response['Cache-Control'], 'no-store')
                self.assertIn(b"We'll be back shortly", response.content)
        downstream.assert_not_called()

    def test_health_remains_available_without_database_or_session_access(self):
        self.assertTrue(self.other_lock(RESET_INTENT))
        downstream = Mock(return_value=JsonResponse({'status': 'ok'}))
        middleware = DemoMaintenanceMiddleware(downstream)
        with self.assertNumQueries(0):
            response = middleware(self.factory.get('/health/'))
        self.assertEqual(response.status_code, 200)
        downstream.assert_not_called()

    def test_existing_request_finishes_before_reset_and_new_access_is_denied(self):
        entered = ThreadEvent()
        finished = ThreadEvent()
        errors = []
        self.assertTrue(self.other_lock(APP_ACTIVITY, shared=True))

        def reset():
            try:
                with demo_reset_lock(timeout=5):
                    entered.set()
            except Exception as error:
                errors.append(error)
            finally:
                connections.close_all()
                finished.set()

        worker = Thread(target=reset)
        worker.start()
        try:
            # Wait for reset intent to be visibly held in the actual database.
            with connection.cursor() as cursor:
                for _ in range(100):
                    cursor.execute(
                        'SELECT count(*) FROM pg_locks WHERE locktype=%s '
                        'AND classid=%s AND objid=%s AND mode=%s AND granted',
                        ['advisory', LOCK_NAMESPACE, RESET_INTENT, 'ExclusiveLock'],
                    )
                    if cursor.fetchone()[0]:
                        break
                    finished.wait(0.02)
                else:
                    self.fail('Reset did not acquire maintenance intent')
            self.assertFalse(entered.is_set())
            with application_access() as admitted:
                self.assertFalse(admitted)
            self.other.close()  # The in-flight request has finished.
            self.assertTrue(finished.wait(5))
            self.assertTrue(entered.is_set())
            self.assertEqual(errors, [])
        finally:
            self.other.close()
            worker.join(timeout=6)

    def test_failed_reset_releases_maintenance_and_allows_normal_requests(self):
        with self.assertRaisesRegex(RuntimeError, 'controlled failure'):
            with demo_reset_lock():
                self.assertFalse(self.other_lock(RESET_INTENT, shared=True))
                raise RuntimeError('controlled failure')
        self.assertTrue(self.other_lock(RESET_INTENT, shared=True))
        self.assertTrue(self.other_lock(APP_ACTIVITY))
        self.other.close()
        response = DemoMaintenanceMiddleware(lambda request: HttpResponse('normal'))(
            self.factory.get('/'),
        )
        self.assertEqual(response.status_code, 200)

    def test_timeout_aborts_before_reset_body_and_reopens_access(self):
        self.assertTrue(self.other_lock(APP_ACTIVITY, shared=True))
        with self.assertRaisesRegex(CommandError, 'did not finish'):
            with demo_reset_lock(timeout=0):
                self.fail('Reset must not start while activity remains')
        with application_access() as admitted:
            self.assertTrue(admitted)

    def test_overlapping_reset_is_rejected(self):
        self.assertTrue(self.other_lock(RESET_INTENT))
        with self.assertRaisesRegex(CommandError, 'already running'):
            with demo_reset_lock():
                self.fail('Second reset must not run')

    def test_event_maintenance_skips_reset_window_without_touching_events(self):
        self.assertTrue(self.other_lock(RESET_INTENT))
        # Only the admission lock query is made, no event update.
        with self.assertNumQueries(1):
            self.assertEqual(complete_past_events(), 0)

    def test_request_failure_releases_activity_lock(self):
        def fail(request):
            raise RuntimeError('request failed')
        with self.assertRaisesRegex(RuntimeError, 'request failed'):
            DemoMaintenanceMiddleware(fail)(self.factory.post('/accounts/signup/'))
        self.assertTrue(self.other_lock(APP_ACTIVITY))

    def test_connection_termination_clears_maintenance_without_persistent_flag(self):
        self.assertTrue(self.other_lock(RESET_INTENT))
        self.assertTrue(self.other_lock(APP_ACTIVITY))
        with application_access() as admitted:
            self.assertFalse(admitted)
        self.other.close()
        with application_access() as admitted:
            self.assertTrue(admitted)
