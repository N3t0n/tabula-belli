from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.core.exceptions import ValidationError


class Game(models.Model):
    """Game catalog for TCGs, TTRPGs and Wargames."""

    class Category(models.TextChoices):
        TCG = "TCG", "TCGs"
        TTRPG = "TTRPG", "TTRPGs"
        WARGAME = "WARGAME", "Wargames"

    name = models.CharField(
        max_length=150,
        help_text="Game name"
    )
    category = models.CharField(
        max_length=15,
        choices=Category.choices,
        help_text="Game category"
    )
    slug = models.SlugField(
        max_length=150,
        unique=True,
        help_text="Auto-generated URL slug (only game name, no category)"
    )
    description = models.TextField(
        blank=True,
        max_length=5000,
        help_text="Game description (max 5000 characters, optional)"
    )

    is_official = models.BooleanField(
        default=False,
        help_text="True if curated by admins, False if player-added"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='added_games',
        help_text="User who created this game (auto-filled, game persists if user deleted)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Game"
        verbose_name_plural = "Games"

        constraints = [
            models.UniqueConstraint(
                models.functions.Lower(models.functions.Trim("name")),
                name="uniq_game_name_global",
                violation_error_message="A game with this name already exists"
            ),
        ]

        indexes = [
            models.Index(fields=["category"]),
            models.Index(models.functions.Lower(
                "name"), name="game_name_ci_idx"),
            models.Index(fields=["category", "name"],
                         name="game_cat_name_idx"),
            models.Index(fields=["is_official", "category"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def save(self, *args, **kwargs):
        if not self.pk and not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        RESERVED_WORDS = {'admin', 'new', 'create', 'edit', 'delete', 'list'}
        MAX_SLUG_LENGTH = 150

        base_slug = slugify(self.name)[:MAX_SLUG_LENGTH]

        if base_slug in RESERVED_WORDS:
            base_slug = f"game-{base_slug}"

        slug = base_slug
        counter = 2

        while Game.objects.filter(slug=slug).exists():
            suffix = f"-{counter}"
            max_base_length = MAX_SLUG_LENGTH - len(suffix)
            truncated_base = base_slug[:max_base_length]
            slug = f"{truncated_base}{suffix}"
            counter += 1

            if counter > 1000:
                raise ValueError(
                    f"Could not generate unique slug for: {self.name}")

        return slug

    def clean(self):
        super().clean()

    @property
    def is_player_added(self):
        return not self.is_official
