from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from apps.events.models import Event, EventRegistration
from cities_light.models import Country, Region, City
from apps.games.models import Game
from apps.players.models import Player


class EventRegistrationStatusTestCase(TestCase):
    """Tests for Event.get_registration_status() and Event.can_register()"""

    def setUp(self):
        """Create base objects for tests"""
        country = Country.objects.create(
            name="Test Country", code2="TC", code3="TST")
        region = Region.objects.create(
            name="Test Region", slug="test-region", country=country)
        city = City.objects.create(
            name="Test City", slug="test-city", region=region, country=country)
        game = Game.objects.create(
            name="Test Game", slug="test-game", category=Game.Category.TCG)

        # Create organizer (Player IS the User model)
        organizer = Player.objects.create_user(
            username="organizer", email="org@test.com", password="pass123")

        now = timezone.now()

        self.event = Event.objects.create(
            title="Test Event",
            slug="test-event",
            country=country,
            city=city,
            game=game,
            organizer=organizer,
            contact_email="contact@test.com",
            start_at=now + timedelta(days=7),
            end_at=now + timedelta(days=7, hours=4),
            capacity=10,
            registration_opens_at=now + timedelta(days=-2),
            registration_closes_at=now + timedelta(days=5),
            status=Event.Status.ACTIVE,
        )
        self.organizer = organizer

    def test_registration_not_open_before_opens_at(self):
        """Status should be NOT_OPEN before registration_opens_at"""
        self.event.registration_opens_at = timezone.now() + timedelta(hours=1)
        self.event.save()

        self.assertEqual(
            self.event.get_registration_status(),
            Event.RegistrationStatus.NOT_OPEN
        )
        self.assertFalse(self.event.can_register())

    def test_registration_open_inside_window(self):
        """Status should be OPEN when inside registration window and not full"""
        self.assertEqual(
            self.event.get_registration_status(),
            Event.RegistrationStatus.OPEN
        )
        self.assertTrue(self.event.can_register())

    def test_registration_full_at_capacity(self):
        """Status should be FULL when confirmed registrations reach capacity"""
        # Create 10 confirmed registrations
        for i in range(10):
            player = Player.objects.create_user(
                username=f"testuser{i}",
                email=f"test{i}@example.com",
                password="testpass123"
            )
            EventRegistration.objects.create(
                event=self.event,
                player=player,
                status=EventRegistration.Status.CONFIRMED
            )

        self.assertEqual(
            self.event.get_registration_status(),
            Event.RegistrationStatus.FULL
        )
        self.assertFalse(self.event.can_register())

    def test_registration_closed_after_closes_at(self):
        """Status should be CLOSED after registration_closes_at"""
        self.event.registration_closes_at = timezone.now() + timedelta(hours=-1)
        self.event.save()

        self.assertEqual(
            self.event.get_registration_status(),
            Event.RegistrationStatus.CLOSED
        )
        self.assertFalse(self.event.can_register())

    def test_registration_closed_when_event_started(self):
        """Status should be CLOSED when event has started"""
        self.event.start_at = timezone.now() + timedelta(hours=-1)
        self.event.save()

        self.assertEqual(
            self.event.get_registration_status(),
            Event.RegistrationStatus.CLOSED
        )
        self.assertFalse(self.event.can_register())

    def test_registration_canceled_when_event_canceled(self):
        """Status should be CANCELED when event.status is CANCELED"""
        self.event.status = Event.Status.CANCELED
        self.event.save()

        self.assertEqual(
            self.event.get_registration_status(),
            Event.RegistrationStatus.CANCELED
        )
        self.assertFalse(self.event.can_register())


class EventModelValidationTestCase(TestCase):
    """Tests for Event.clean() validation"""

    def setUp(self):
        """Create base objects"""
        country = Country.objects.create(
            name="Test Country", code2="TC", code3="TST")
        region = Region.objects.create(
            name="Test Region", slug="test-region", country=country)
        city = City.objects.create(
            name="Test City", slug="test-city", region=region, country=country)
        game = Game.objects.create(
            name="Test Game", slug="test-game", category=Game.Category.TCG)

        # Create organizer (Player IS the User model)
        organizer = Player.objects.create_user(
            username="organizer", email="org@test.com", password="pass123")

        self.country = country
        self.city = city
        self.game = game
        self.organizer = organizer

    def test_clean_passes_with_valid_dates(self):
        """Event.clean() should pass with valid dates (opens < closes < start)"""
        now = timezone.now()

        event = Event(
            title="Valid Event",
            slug="valid-event",
            country=self.country,
            city=self.city,
            game=self.game,
            organizer=self.organizer,
            contact_email="contact@test.com",
            start_at=now + timedelta(days=7),
            end_at=now + timedelta(days=7, hours=4),
            capacity=10,
            registration_opens_at=now + timedelta(days=1),
            registration_closes_at=now + timedelta(days=5),
        )

        # Should not raise
        event.clean()

    def test_clean_fails_with_invalid_dates(self):
        """Event.clean() should raise ValidationError with invalid dates"""
        now = timezone.now()

        # Case 1: opens_at after closes_at
        event = Event(
            title="Invalid Event",
            slug="invalid-event",
            country=self.country,
            city=self.city,
            game=self.game,
            organizer=self.organizer,
            contact_email="contact@test.com",
            start_at=now + timedelta(days=7),
            end_at=now + timedelta(days=7, hours=4),
            capacity=10,
            registration_opens_at=now + timedelta(days=6),
            registration_closes_at=now + timedelta(days=1),
        )

        with self.assertRaises(ValidationError):
            event.clean()


class EventUserFormTestCase(TestCase):
    """Tests for EventUserForm validation and defaults"""

    def setUp(self):
        """Create base objects for form tests"""
        country = Country.objects.create(
            name="Test Country", code2="TC", code3="TST")
        region = Region.objects.create(
            name="Test Region", slug="test-region", country=country)
        city = City.objects.create(
            name="Test City", slug="test-city", region=region, country=country)
        game = Game.objects.create(
            name="Test Game", slug="test-game", category=Game.Category.TCG)

        organizer = Player.objects.create_user(
            username="organizer", email="org@test.com", password="pass123")

        self.country = country
        self.region = region
        self.city = city
        self.game = game
        self.organizer = organizer

    def test_form_requires_start_24h_in_future_on_create(self):
        """EventUserForm should require start_at at least 24h in future on creation"""
        from apps.events.forms import EventUserForm

        now = timezone.now()
        start = now + timedelta(hours=12)  # Only 12h in future (invalid)

        form = EventUserForm(data={
            'title': 'Test Event',
            'event_type': 'TOURNAMENT',
            'start_at': start.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (start + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 32,
            'price': '0.00',
            'country': self.country.pk,
            'city': self.city.pk,
            'game': self.game.pk,
            'contact_email': 'test@example.com',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('start_at', form.errors)
        self.assertIn('24 hours', str(form.errors['start_at']))

    def test_form_applies_defaults_when_both_empty(self):
        """EventUserForm should apply defaults when both registration fields empty"""
        from apps.events.forms import EventUserForm

        now = timezone.now()
        start = now + timedelta(days=10)

        form = EventUserForm(data={
            'title': 'Test Event',
            'event_type': 'TOURNAMENT',
            'start_at': start.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (start + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 32,
            'price': '0.00',
            'country': self.country.pk,
            'city': self.city.pk,
            'game': self.game.pk,
            'contact_email': 'test@example.com',
            # registration_opens_at and closes_at NOT provided
        })

        self.assertTrue(form.is_valid())

        # Verify defaults were applied
        opens = form.cleaned_data.get('registration_opens_at')
        closes = form.cleaned_data.get('registration_closes_at')
        start_cleaned = form.cleaned_data.get('start_at')

        self.assertIsNotNone(opens)
        self.assertIsNotNone(closes)

        # opens should be ~now (with margin for test execution)
        self.assertTrue(abs((opens - now).total_seconds()) < 10)

        # closes should be exactly start - 24h (using cleaned start_at from form)
        expected_close = start_cleaned - timedelta(hours=24)
        self.assertEqual(closes, expected_close)

    def test_form_validates_opens_before_closes(self):
        """EventUserForm should validate opens < closes"""
        from apps.events.forms import EventUserForm

        now = timezone.now()
        start = now + timedelta(days=10)

        form = EventUserForm(data={
            'title': 'Test Event',
            'event_type': 'TOURNAMENT',
            'start_at': start.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (start + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
            'registration_opens_at': (start - timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M'),
            # BEFORE opens (invalid)
            'registration_closes_at': (start - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 32,
            'price': '0.00',
            'country': self.country.pk,
            'city': self.city.pk,
            'game': self.game.pk,
            'contact_email': 'test@example.com',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('registration_closes_at', form.errors)

    def test_form_validates_closes_before_start(self):
        """EventUserForm should validate closes < start"""
        from apps.events.forms import EventUserForm

        now = timezone.now()
        start = now + timedelta(days=10)

        form = EventUserForm(data={
            'title': 'Test Event',
            'event_type': 'TOURNAMENT',
            'start_at': start.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (start + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
            'registration_opens_at': now.strftime('%Y-%m-%dT%H:%M'),
            # AFTER start (invalid)
            'registration_closes_at': (start + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 32,
            'price': '0.00',
            'country': self.country.pk,
            'city': self.city.pk,
            'game': self.game.pk,
            'contact_email': 'test@example.com',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('registration_closes_at', form.errors)

    def test_form_accepts_location_ids_as_strings(self):
        """EventUserForm should accept the string IDs provided by HTTP POST."""
        from apps.events.forms import EventUserForm

        start = timezone.now() + timedelta(days=10)
        form = EventUserForm(data={
            'title': 'Test Event',
            'event_type': 'TOURNAMENT',
            'start_at': start.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (start + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 32,
            'price': '0.00',
            'country': str(self.country.pk),
            'region': str(self.region.pk),
            'city': str(self.city.pk),
            'game': str(self.game.pk),
            'contact_email': 'test@example.com',
        })

        self.assertTrue(form.is_valid(), form.errors)

    def test_form_handles_non_numeric_location_ids_without_exception(self):
        """Invalid location IDs should produce form errors, not AttributeError."""
        from apps.events.forms import EventUserForm

        start = timezone.now() + timedelta(days=10)
        form = EventUserForm(data={
            'title': 'Test Event',
            'event_type': 'TOURNAMENT',
            'start_at': start.strftime('%Y-%m-%dT%H:%M'),
            'end_at': (start + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
            'capacity': 32,
            'price': '0.00',
            'country': 'not-a-number',
            'region': 'not-a-number',
            'city': str(self.city.pk),
            'game': str(self.game.pk),
            'contact_email': 'test@example.com',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('country', form.errors)
        self.assertIn('region', form.errors)
