"""
Event domain services.
Business logic that operates on events but doesn't belong to a single model.
"""
import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from config.demo_maintenance import application_access

logger = logging.getLogger(__name__)


def derive_initial_status(end_at):
    """Determine initial event status based on end date."""
    from apps.events.models import Event

    now = timezone.now()
    return Event.Status.COMPLETED if end_at <= now else Event.Status.ACTIVE


def complete_past_events():
    """Mark past events completed, skipping a run during demo maintenance."""
    from apps.events.models import Event

    with application_access() as admitted:
        if not admitted:
            logger.info('Demo maintenance in progress; event completion skipped')
            return 0
        with transaction.atomic():
            now = timezone.now()
            updated = Event.objects.filter(
                status=Event.Status.ACTIVE,
                end_at__lte=now,
            ).update(status=Event.Status.COMPLETED, updated_at=now)

        if updated > 0:
            logger.info('Auto-completed %s past events', updated)
        return updated


@transaction.atomic
def cancel_event(event):
    """Cancel an event and all its confirmed registrations atomically."""
    from apps.events.models import Event, EventRegistration

    locked_event = Event.objects.select_for_update().get(pk=event.pk)

    if not locked_event.is_editable():
        if locked_event.status != Event.Status.ACTIVE:
            reason = f"it has status {locked_event.get_status_display()}"
        else:
            reason = "it has already started"

        raise ValidationError(
            f"Cannot cancel this event because {reason}"
        )

    cancelled_at = timezone.now()
    EventRegistration.objects.filter(
        event=locked_event,
        status=EventRegistration.Status.CONFIRMED,
    ).update(
        status=EventRegistration.Status.CANCELLED,
        cancelled_at=cancelled_at,
        updated_at=cancelled_at,
    )

    locked_event.status = Event.Status.CANCELED
    locked_event.save(update_fields=['status', 'updated_at'])

    return locked_event


@transaction.atomic
def cancel_registration_for_actor(registration, actor):
    """Cancel registration if actor has permission."""
    from apps.events.models import Event

    if not registration.can_be_cancelled_by(actor):
        if not registration.event.is_editable():
            if registration.event.status in [Event.Status.COMPLETED, Event.Status.CANCELED]:
                reason = f"the event is {registration.event.get_status_display().lower()}"
            else:
                reason = "the event has already started"
        else:
            reason = "you dont have permission"

        raise ValidationError(
            f"Cannot cancel this registration because {reason}."
        )

    registration.cancel()

    logger.info(
        "Registration %s cancelled for event %s by an authorized actor",
        registration.id,
        registration.event_id,
    )
