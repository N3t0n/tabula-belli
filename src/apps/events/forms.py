from django import forms
from django.core.exceptions import ValidationError
from apps.events.models import Event
from cities_light.models import Region, City


def _parse_model_id(value):
    if value in (None, '') or isinstance(value, bool):
        return None

    if not isinstance(value, (int, str)):
        return None

    try:
        return int(value)
    except ValueError:
        return None


class EventAdminForm(forms.ModelForm):
    """Admin form with HTMX-powered cascading location fields."""

    class Meta:
        model = Event
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['region'].queryset = Region.objects.none()
        self.fields['city'].queryset = City.objects.none()
        self.fields['region'].required = False

        if self.is_bound:
            country_id = self.data.get('country')
            region_id = self.data.get('region')

            if country_id:
                try:
                    self.fields['region'].queryset = Region.objects.filter(
                        country_id=country_id
                    ).order_by('name')
                except (ValueError, TypeError):
                    pass

            if country_id and region_id:
                try:
                    self.fields['city'].queryset = City.objects.filter(
                        country_id=country_id,
                        region_id=region_id
                    ).order_by('name')
                except (ValueError, TypeError):
                    pass
            elif country_id:
                try:
                    self.fields['city'].queryset = City.objects.filter(
                        country_id=country_id
                    ).order_by('name')
                except (ValueError, TypeError):
                    pass

        # If editing existing event, load current location data
        elif self.instance.pk:
            if self.instance.country:
                self.fields['region'].queryset = Region.objects.filter(
                    country=self.instance.country
                ).order_by('name')

            if self.instance.region:
                self.fields['city'].queryset = City.objects.filter(
                    region=self.instance.region
                ).order_by('name')
            elif self.instance.country:
                # Handle countries without regions (e.g., Vatican)
                self.fields['city'].queryset = City.objects.filter(
                    country=self.instance.country
                ).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        city = cleaned_data.get('city')

        if city:
            cleaned_data['country'] = city.country
            cleaned_data['region'] = city.region

        return cleaned_data


class EventUserForm(forms.ModelForm):
    """Frontend form for Event with cascading location fields."""

    class Meta:
        model = Event
        fields = [
            'event_type', 'title', 'description',
            'country', 'region', 'city',
            'location_name', 'location_address',
            'start_at', 'end_at',
            'registration_opens_at', 'registration_closes_at',
            'capacity', 'price', 'game', 'contact_email'
        ]
        widgets = {
            'start_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-input'
            }, format='%Y-%m-%dT%H:%M'),
            'end_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-input'
            }, format='%Y-%m-%dT%H:%M'),
            'registration_opens_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-input'
            }, format='%Y-%m-%dT%H:%M'),
            'registration_closes_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-input'
            }, format='%Y-%m-%dT%H:%M'),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'organizer@example.com'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make registration dates optional in form (defaults applied in clean())
        self.fields['contact_email'].required = True
        self.fields['registration_opens_at'].required = False
        self.fields['registration_closes_at'].required = False

        self.fields['region'].queryset = Region.objects.none()
        self.fields['city'].queryset = City.objects.none()
        self.fields['region'].required = False

        if self.is_bound:
            country_id = _parse_model_id(self.data.get('country'))
            region_id = _parse_model_id(self.data.get('region'))

            # Load regions based on country (with fallback)
            regions_qs = Region.objects.all().order_by('name')
            if country_id is not None:
                regions_qs = regions_qs.filter(country_id=country_id)
            self.fields['region'].queryset = regions_qs

            # Load cities based on region (preferred) or country (fallback)
            cities_qs = City.objects.all().order_by('name')
            if region_id is not None:
                cities_qs = cities_qs.filter(region_id=region_id)
            elif country_id is not None:
                cities_qs = cities_qs.filter(country_id=country_id)
            self.fields['city'].queryset = cities_qs

        # If editing existing event, load current location data
        elif self.instance.pk:
            if self.instance.country:
                self.fields['region'].queryset = Region.objects.filter(
                    country=self.instance.country
                ).order_by('name')

            if self.instance.region:
                self.fields['city'].queryset = City.objects.filter(
                    region=self.instance.region
                ).order_by('name')
            elif self.instance.country:
                # Handle countries without regions (e.g., Vatican)
                self.fields['city'].queryset = City.objects.filter(
                    country=self.instance.country
                ).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        city = cleaned_data.get('city')

        if city:
            cleaned_data['country'] = city.country
            cleaned_data['region'] = city.region

        # Registration date validation and defaults
        from django.utils import timezone
        from datetime import timedelta

        start_at = cleaned_data.get('start_at')
        registration_opens_at = cleaned_data.get('registration_opens_at')
        registration_closes_at = cleaned_data.get('registration_closes_at')
        now = timezone.now()

        # Validate event start time on creation
        if not self.instance.pk and start_at:
            if start_at < now + timedelta(hours=24):
                raise ValidationError({
                    'start_at': 'Event must start at least 24 hours in the future'
                })

        # Set default registration dates if not provided
        if not registration_opens_at and not registration_closes_at:
            if start_at:
                # Opens now, closes 24h before event
                cleaned_data['registration_opens_at'] = now
                cleaned_data['registration_closes_at'] = start_at - \
                    timedelta(hours=24)
                registration_opens_at = cleaned_data['registration_opens_at']
                registration_closes_at = cleaned_data['registration_closes_at']

        # Validate registration window timing
        if registration_opens_at and registration_closes_at:
            if registration_opens_at >= registration_closes_at:
                raise ValidationError({
                    'registration_closes_at': 'Registration must close after it opens'
                })

        if registration_closes_at and start_at:
            if registration_closes_at >= start_at:
                raise ValidationError({
                    'registration_closes_at': 'Registration must close before the event starts'
                })

        return cleaned_data

    def clean_end_at(self):
        """Prevent creating events with past end dates."""
        from django.utils import timezone

        end_at = self.cleaned_data['end_at']
        now = timezone.now()

        # Only validate on creation (not on edit)
        if not self.instance.pk:
            if end_at < now:
                raise ValidationError(
                    "Event end date must be in the future. "
                    "Cannot create events that have already ended."
                )

        return end_at
