"""Coordinate demo resets and application access using PostgreSQL session locks.

No persistent maintenance flag: PostgreSQL releases locks if the process dies.
All participating connections must connect directly to PostgreSQL (no transaction
pooler), as the session owns each lock across queries and transactions.
"""
from contextlib import contextmanager
from time import monotonic, sleep

from django.core.management.base import CommandError
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string

# Two application-owned advisory keys: reset intent and in-flight activity.
LOCK_NAMESPACE = 141363
RESET_INTENT = 1
APP_ACTIVITY = 2


def _try_lock(key, shared=False):
    function = 'pg_try_advisory_lock_shared' if shared else 'pg_try_advisory_lock'
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT {function}(%s, %s)', [LOCK_NAMESPACE, key])
        return cursor.fetchone()[0]


def _unlock(key, shared=False):
    function = 'pg_advisory_unlock_shared' if shared else 'pg_advisory_unlock'
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT {function}(%s, %s)', [LOCK_NAMESPACE, key])
    except Exception:
        # An unusable/aborted connection cannot retain a maintenance lock.
        connection.close()
        raise


@contextmanager
def application_access():
    """Admit activity without waiting, or yield False during maintenance."""
    if connection.vendor != 'postgresql':
        yield True
        return
    if not _try_lock(RESET_INTENT, shared=True):
        yield False
        return
    admitted = False
    try:
        admitted = _try_lock(APP_ACTIVITY, shared=True)
    finally:
        _unlock(RESET_INTENT, shared=True)
    try:
        yield admitted
    finally:
        if admitted:
            _unlock(APP_ACTIVITY, shared=True)


@contextmanager
def demo_reset_lock(timeout=30):
    """Reject overlapping resets; stop new access and drain existing activity."""
    if not _try_lock(RESET_INTENT):
        raise CommandError('Another demo reset is already running; no data changed.')
    acquired = False
    try:
        deadline = monotonic() + timeout
        while not acquired:
            acquired = _try_lock(APP_ACTIVITY)
            if not acquired:
                if monotonic() >= deadline:
                    raise CommandError(
                        'Application activity did not finish in time; reset aborted.'
                    )
                sleep(0.1)
        yield
    finally:
        try:
            if acquired:
                _unlock(APP_ACTIVITY)
        finally:
            _unlock(RESET_INTENT)


class DemoMaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Keep Northflank liveness probes green during intentional maintenance.
        if request.path == '/health/':
            return JsonResponse({'status': 'ok'})
        with application_access() as admitted:
            if admitted:
                return self.get_response(request)
            # Deliberately no request context: auth/session/context processors
            # must not touch the database while maintenance is active.
            response = HttpResponse(
                render_to_string('503.html'), status=503,
            )
            response['Retry-After'] = '60'
            response['Cache-Control'] = 'no-store'
            return response
