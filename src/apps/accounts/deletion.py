"""Review and execute account deletion without discarding event history."""
from dataclasses import dataclass
import hashlib
import json

from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.demo import DEMO_ACCOUNT_NOTICE, is_public_demo_user
from apps.events.models import Event, EventRegistration
from apps.players.models import Player


IN_PROGRESS_ERROR = (
    'You cannot delete your account while an event you organize is in progress. '
    'Please try again after it finishes.'
)
SUPERUSER_ERROR = (
    'Superuser accounts cannot be deleted from the frontend. '
    'Use Django admin instead.'
)
REVIEW_ERROR = 'Your account or events have changed. Please review the deletion details again.'
TOKEN_SALT = 'accounts.delete-account'


class AccountDeletionBlocked(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


@dataclass
class DeletionReview:
    events: list
    registrations: list
    in_progress: list
    future_events: list
    pending_registrations: list
    fingerprint: str

    @property
    def has_pending(self):
        return bool(self.future_events or self.pending_registrations)


def _review(user, events, registrations, now):
    owned = [event for event in events if event.organizer_id == user.pk]
    event_map = {event.pk: event for event in events}
    in_progress = [event for event in owned if (
        event.status == Event.Status.ACTIVE and event.start_at <= now < event.end_at
    )]
    future = [event for event in owned if (
        event.status == Event.Status.ACTIVE and event.start_at > now
    )]
    pending = [reg for reg in registrations if (
        reg.status == EventRegistration.Status.CONFIRMED
        and reg.event_id in event_map
        and event_map[reg.event_id].status == Event.Status.ACTIVE
        and event_map[reg.event_id].end_at > now
    )]
    # Bind confirmation to the actual records, including timing boundaries.
    payload = {
        'user': [user.pk, user.username, user.email, user.is_superuser],
        'events': [[e.pk, e.title, e.organizer_id, e.status, e.start_at.isoformat(),
                    e.end_at.isoformat(), e.updated_at.isoformat()] for e in events],
        'registrations': [[r.pk, r.event_id, r.status, r.updated_at.isoformat()]
                          for r in registrations],
        'in_progress': [e.pk for e in in_progress],
        'future': [e.pk for e in future],
        'pending': [r.pk for r in pending],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return DeletionReview(owned, registrations, in_progress, future, pending, digest)


def deletion_review(user):
    registrations = list(user.event_registrations.order_by('pk'))
    events = list(Event.objects.filter(
        Q(organizer_id=user.pk) | Q(pk__in=[r.event_id for r in registrations])
    ).order_by('pk'))
    return _review(user, events, registrations, timezone.now())


def confirmation_token(user, review):
    return signing.dumps({'user': user.pk, 'fingerprint': review.fingerprint}, salt=TOKEN_SALT)


@transaction.atomic
def delete_account(user_id, token):
    user = Player.objects.select_for_update(no_key=True).filter(pk=user_id).first()
    if user is None:
        return  # A concurrent confirmed deletion already completed.
    if is_public_demo_user(user):
        raise AccountDeletionBlocked(DEMO_ACCOUNT_NOTICE, 403)
    if user.is_superuser:
        raise AccountDeletionBlocked(SUPERUSER_ERROR, 403)

    # Serialize deletion and registration for this user, then lock events in a
    # stable order before registrations. NO KEY UPDATE avoids a deadlock with
    # concurrent FK inserts; a late protected relation makes deletion roll back.
    registered_ids = list(user.event_registrations.values_list('event_id', flat=True))
    events = list(Event.objects.select_for_update().filter(
        Q(organizer_id=user.pk) | Q(pk__in=registered_ids)
    ).order_by('pk'))
    registrations = list(user.event_registrations.select_for_update().order_by('pk'))
    now = timezone.now()
    review = _review(user, events, registrations, now)
    if review.in_progress:
        raise AccountDeletionBlocked(IN_PROGRESS_ERROR)
    try:
        signed = signing.loads(token, salt=TOKEN_SALT, max_age=15 * 60)
    except (signing.BadSignature, TypeError, ValueError):
        raise AccountDeletionBlocked(REVIEW_ERROR) from None
    if signed != {'user': user.pk, 'fingerprint': review.fingerprint}:
        raise AccountDeletionBlocked(REVIEW_ERROR)

    future_ids = [event.pk for event in review.future_events]
    EventRegistration.objects.filter(
        event_id__in=future_ids, status=EventRegistration.Status.CONFIRMED,
    ).update(status=EventRegistration.Status.CANCELLED, cancelled_at=now, updated_at=now)
    Event.objects.filter(pk__in=future_ids).update(status=Event.Status.CANCELED, updated_at=now)

    EventRegistration.objects.filter(
        pk__in=[reg.pk for reg in review.pending_registrations],
        status=EventRegistration.Status.CONFIRMED,
    ).update(status=EventRegistration.Status.CANCELLED, cancelled_at=now, updated_at=now)

    # A scheduler delay must not leave an ended event ACTIVE or block deletion.
    Event.objects.filter(
        organizer_id=user.pk, status=Event.Status.ACTIVE, end_at__lte=now,
    ).update(status=Event.Status.COMPLETED, updated_at=now)

    Event.objects.filter(organizer_id=user.pk).update(
        organizer=None, contact_email='', updated_at=now,
    )
    EventRegistration.objects.filter(player_id=user.pk).update(player=None)
    user.delete()
