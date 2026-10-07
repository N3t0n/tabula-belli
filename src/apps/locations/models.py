from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower, Trim


class LocationMixin(models.Model):
    """Adds country, region, city fields from django-cities-light."""

    country = models.ForeignKey(
        'cities_light.Country',
        on_delete=models.SET_NULL,
        verbose_name="Country",
        blank=True,
        null=True,
        related_name='+',
        help_text="Select your country"
    )

    region = models.ForeignKey(
        'cities_light.Region',
        on_delete=models.SET_NULL,
        verbose_name="Region",
        blank=True,
        null=True,
        related_name='+',
        help_text="Select your region/state"
    )

    city = models.ForeignKey(
        'cities_light.City',
        on_delete=models.PROTECT,
        verbose_name="City",
        blank=True,
        null=True,
        related_name='+',
        help_text="Select your city"
    )

    class Meta:
        abstract = True

    def get_location_display(self):
        parts = []
        if self.city:
            parts.append(self.city.name)
        if self.region:
            parts.append(self.region.name)
        if self.country:
            parts.append(self.country.name)

        return ", ".join(parts) if parts else "Not specified"

    def get_city_name(self):
        return self.city.name if self.city else ""

    def has_location(self):
        return bool(self.country or self.region or self.city)
