from django.db import IntegrityError, models, transaction
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta
from apps.locations.models import LocationMixin


class Event(LocationMixin, models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELED = 'CANCELED', 'Canceled'

    class EventType(models.TextChoices):
        CASUAL = 'CASUAL', 'Casual Event'
        TOURNAMENT = 'TOURNAMENT', 'Competitive Tournament'

    class RegistrationStatus(models.TextChoices):
        NOT_OPEN = "NOT_OPEN", "Registration not open yet"
        OPEN = "OPEN", "Registration open"
        CLOSED = "CLOSED", "Registration closed"
        FULL = "FULL", "Event at full capacity"
        CANCELED = "CANCELED", "Event canceled"

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        default=EventType.CASUAL,
        db_index=True,
        help_text='Type of event: casual or tournament'
    )

    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True
    )
    description = models.TextField(blank=True)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)
    capacity = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10000)],
        help_text='Number of participants (1-10000)'
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0.00,
        blank=True,
        null=True,
        help_text='Entry fee in euros. Leave empty or 0 for free events.'
    )
    registration_opens_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Opens registration (empty = now)"
    )
    registration_closes_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Closes registration (empty = event start)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    country = models.ForeignKey(
        'cities_light.Country',
        on_delete=models.PROTECT,
        verbose_name="Country",
        blank=False,
        null=False,
        related_name='+',
        help_text="Event country (required)"
    )

    region = models.ForeignKey(
        'cities_light.Region',
        on_delete=models.PROTECT,
        verbose_name="Region",
        blank=True,
        null=True,
        related_name='+',
        help_text="Region/state (optional)"
    )

    city = models.ForeignKey(
        'cities_light.City',
        on_delete=models.PROTECT,
        verbose_name="City",
        blank=False,
        null=False,  # Always required
        related_name='+',
        help_text="Event city (required)"
    )

    # Specific location within the city
    location_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Location Name",
        help_text="Venue name"
    )

    location_address = models.TextField(
        blank=True,
        verbose_name="Location Address",
        help_text="Venue address"
    )

    # Relationships
    game = models.ForeignKey(
        'games.Game',
        on_delete=models.PROTECT,
        related_name='events',
        help_text='Game played in this event'
    )

    organizer = models.ForeignKey(
        'players.Player',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='organized_events',
        help_text='Organizer of this event'
    )

    contact_email = models.EmailField(
        verbose_name='Contact email',
        help_text='Contact email for players',
        blank=True
    )

    class Meta:
        db_table = 'events'
        verbose_name = 'Event'
        verbose_name_plural = 'Events'
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status='ACTIVE') | models.Q(organizer__isnull=False),
                name='active_event_has_organizer',
                violation_error_message='An active event needs an organizer',
            ),
            models.CheckConstraint(
                check=models.Q(capacity__gte=1) & models.Q(
                    capacity__lte=10000),
                name='events_capacity_range',
                violation_error_message='Capacity must be between 1 and 10000'
            ),
            models.CheckConstraint(
                check=models.Q(end_at__gt=models.F('start_at')),
                name='events_end_after_start',
                violation_error_message='Event must end after it starts'
            )
        ]
        indexes = [
            models.Index(
                fields=['status', 'start_at'],
                name='events_status_date_idx'
            ),
            models.Index(
                fields=['status', 'country', 'start_at'],
                name='events_country_idx'
            ),
            models.Index(
                fields=['status', 'city', 'start_at'],
                name='events_city_idx'
            ),
            models.Index(
                fields=['game', 'status', 'start_at'],
                name='events_game_idx'
            ),
            models.Index(
                fields=['event_type', 'status', 'start_at'],
                name='events_type_idx'
            ),
        ]

    def clean(self):
        if self.organizer_id and not self.contact_email:
            raise ValidationError({'contact_email': 'A contact email is required.'})
        super().clean()

        if self.city_id and self.region_id:
            if self.city.region_id != self.region_id:
                raise ValidationError({
                    'city': f'City "{self.city.name}" does not belong to region "{self.region.name}"'
                })

        if self.region_id and self.country_id:
            if self.region.country_id != self.country_id:
                raise ValidationError({
                    'region': f'Region "{self.region.name}" does not belong to country "{self.country.name}"'
                })

        if self.registration_opens_at and self.registration_closes_at:
            if self.registration_opens_at >= self.registration_closes_at:
                raise ValidationError({
                    'registration_closes_at': 'Registration must close after it opens'
                })

            if self.registration_closes_at >= self.start_at:
                raise ValidationError({
                    'registration_closes_at': 'Registration must close before event starts'
                })

        if self.start_at and self.end_at:
            if self.end_at <= self.start_at:
                raise ValidationError({
                    'end_at': 'Event must end after it starts'
                })

        now = timezone.now()

        # Validate COMPLETED status timing
        if self.status == Event.Status.COMPLETED:
            if self.end_at > now:
                raise ValidationError({
                    'status': 'You cannot mark an event as COMPLETED before it has finished.'
                })

        # Validate ACTIVE events are in the future
        if self.status == Event.Status.ACTIVE:
            if self.end_at <= now:
                raise ValidationError({
                    'end_at': 'ACTIVE events cannot have an end date in the past. '
                              'This event should be marked as COMPLETED.'
                })

        # Prevent changes to final event states
        if self.pk:
            try:
                old = Event.objects.get(pk=self.pk)
            except Event.DoesNotExist:
                return

            # If event is in a final state, status cannot change
            if old.status in [Event.Status.COMPLETED, Event.Status.CANCELED]:
                if old.status != self.status:
                    raise ValidationError({
                        'status': f'Cannot change status from {old.get_status_display()}. '
                        'This is a final state.'
                    })

            # Specifically block CANCELED → COMPLETED (makes no sense)
            if old.status == Event.Status.CANCELED and self.status == Event.Status.COMPLETED:
                raise ValidationError({
                    'status': 'Cannot mark a cancelled event as completed.'
                })

    def _generate_unique_slug(self):
        base_slug = slugify(self.title) or "event"
        slug = base_slug
        counter = 2

        Model = self.__class__

        while Model.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

            if counter > 1000:
                raise ValueError(
                    f"Could not generate unique slug for: {self.title}")

        return slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()

        super().save(*args, **kwargs)

    def get_registration_status(self):
        """Return the current registration status for this event."""
        now = timezone.now()

        if self.status == self.Status.CANCELED:
            return self.RegistrationStatus.CANCELED

        if now >= self.start_at:
            return self.RegistrationStatus.CLOSED

        if self.registration_opens_at and now < self.registration_opens_at:
            return self.RegistrationStatus.NOT_OPEN

        if self.registration_closes_at and now >= self.registration_closes_at:
            return self.RegistrationStatus.CLOSED

        if hasattr(self, 'participants_count'):
            confirmed_count = self.participants_count
        else:
            confirmed_count = self.registrations.filter(
                status=EventRegistration.Status.CONFIRMED
            ).count()

        if confirmed_count >= self.capacity:
            return self.RegistrationStatus.FULL

        return self.RegistrationStatus.OPEN

    def can_register(self):
        """Check if registration is currently allowed."""
        return self.get_registration_status() == self.RegistrationStatus.OPEN

    def is_editable(self):
        """Check if this event can be edited or canceled."""
        # Check final states
        if self.status in [self.Status.COMPLETED, self.Status.CANCELED]:
            return False

        # Check if already started
        if self.start_at and self.start_at <= timezone.now():
            return False

        return True

    def __str__(self):
        return f"{self.title} ({self.get_event_type_display()}) - {self.get_location_display()}"

    @property
    def organizer_display(self):
        return self.organizer.username if self.organizer_id else 'Deleted account'


class EventRegistration(models.Model):

    class Status(models.TextChoices):
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    event = models.ForeignKey(
        'Event',
        on_delete=models.CASCADE,
        related_name='registrations',
        help_text='Event for this registration'
    )
    player = models.ForeignKey(
        'players.Player',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='event_registrations',
        help_text='Player who registered'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
        db_index=True,
        help_text='Current registration status'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='When registration was created'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Last status change'
    )
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Cancellation timestamp'
    )

    class Meta:
        db_table = 'event_registrations'
        verbose_name = 'Event Registration'
        verbose_name_plural = 'Event Registrations'
        ordering = ['-created_at']

        constraints = [
            models.UniqueConstraint(
                fields=['event', 'player'],
                condition=models.Q(status='CONFIRMED'),
                name='unique_active_registration'
            ),
        ]

        indexes = [
            models.Index(
                fields=['event', 'status'],
                name='idx_event_status'
            ),
            models.Index(
                fields=['player', 'status'],
                name='idx_player_status'
            ),
            models.Index(
                fields=['created_at'],
                name='idx_created_at'
            ),
        ]

    def __str__(self):
        return f"{self.player_display} → {self.event.title} ({self.get_status_display()})"

    @property
    def player_display(self):
        return self.player.username if self.player_id else 'Deleted account'

    def cancel(self):
        if self.status == self.Status.CANCELLED:
            raise ValidationError("Registration is already cancelled")

        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.save(update_fields=['status', 'cancelled_at', 'updated_at'])

    def can_be_cancelled_by(self, user):
        """Check if user can cancel this registration."""
        if not self.event.is_editable():
            return False

        return (
            self.player == user or
            self.event.organizer == user or
            user.is_superuser
        )

    @classmethod
    def register(cls, *, event, player):
        """Register player for event with validation."""
        with transaction.atomic():
            # Use the same user -> event lock order as account deletion.
            from apps.players.models import Player
            try:
                player = Player.objects.select_for_update().get(pk=player.pk)
            except Player.DoesNotExist:
                raise ValidationError('This account no longer exists. Please sign in again.') from None
            locked_event = Event.objects.select_for_update().get(pk=event.pk)
            registration_status = locked_event.get_registration_status()

            if registration_status == Event.RegistrationStatus.CANCELED:
                raise ValidationError("Cannot register for a canceled event.")

            if registration_status == Event.RegistrationStatus.CLOSED:
                raise ValidationError("Registration is closed.")

            if registration_status == Event.RegistrationStatus.NOT_OPEN:
                if locked_event.registration_opens_at:
                    raise ValidationError(
                        "Registration opens on "
                        f"{locked_event.registration_opens_at.strftime('%Y-%m-%d %H:%M')}"
                    )
                raise ValidationError("Registration is not open yet.")

            if registration_status == Event.RegistrationStatus.FULL:
                raise ValidationError(
                    f"Event is full (capacity: {locked_event.capacity})")

            existing = cls.objects.filter(
                event=locked_event,
                player=player,
                status=cls.Status.CONFIRMED
            ).first()

            if existing:
                raise ValidationError(
                    "You are already registered for this event")

            try:
                with transaction.atomic():
                    return cls.objects.create(
                        event=locked_event,
                        player=player,
                        status=cls.Status.CONFIRMED
                    )
            except IntegrityError as error:
                cause = error.__cause__
                constraint_name = getattr(
                    getattr(cause, 'diag', None), 'constraint_name', None
                )

                if constraint_name not in (None, 'unique_active_registration'):
                    raise

                active_registration_exists = cls.objects.filter(
                    event=locked_event,
                    player=player,
                    status=cls.Status.CONFIRMED
                ).exists()

                if constraint_name == 'unique_active_registration' or active_registration_exists:
                    raise ValidationError(
                        "You are already registered for this event") from error

                raise
