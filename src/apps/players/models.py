from django.db import models
from django.contrib.auth.models import AbstractUser
from apps.games.models import Game
from apps.locations.models import LocationMixin

# Create your models here.


class Player(AbstractUser, LocationMixin):

    email = models.EmailField(unique=True)

    favorite_games = models.ManyToManyField(
        Game,
        blank=True,
        related_name='players'
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        location = self.get_location_display()
        if location != "Not specified":
            return f"{self.username} ({location})"
        return self.username
