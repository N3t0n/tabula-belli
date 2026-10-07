from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import Player


@admin.register(Player)
class PlayerAdmin(BaseUserAdmin):

    list_display = [
        'username',
        'email',
        'full_name',
        'location_display',
        'favorite_games_count',
        'is_staff',
        'is_active',
        'date_joined'
    ]

    list_filter = [
        'is_staff',
        'is_superuser',
        'is_active',
        ('country', admin.RelatedOnlyFieldListFilter),
        ('region', admin.RelatedOnlyFieldListFilter),
        ('city', admin.RelatedOnlyFieldListFilter),
        'date_joined',
    ]

    search_fields = [
        'username',
        'email',
        'first_name',
        'last_name',
        'country__name',
        'region__name',
        'city__name'
    ]

    ordering = ['-date_joined']

    date_hierarchy = 'date_joined'

    list_per_page = 50

    fieldsets = (
        (None, {
            'fields': ('username', 'password')
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'email')
        }),
        ('Location', {
            'fields': ('country', 'region', 'city'),
            'description': 'Geographic information for this player'
        }),
        ('Gaming Preferences', {
            'fields': ('favorite_games',)
        }),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions'
            ),
            'classes': ('collapse',)
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
        ('Optional', {
            'fields': ('first_name', 'last_name', 'country', 'region', 'city')
        }),
    )

    readonly_fields = ['date_joined', 'last_login', 'updated_at']

    filter_horizontal = ['favorite_games', 'groups', 'user_permissions']

    autocomplete_fields = ['country', 'region', 'city']

    @admin.display(description='Full Name')
    def full_name(self, obj):
        name = obj.get_full_name()
        return name if name else format_html('<span style="color: #999;">-</span>')

    @admin.display(description='Location')
    def location_display(self, obj):
        location = obj.get_location_display()
        if location == "Not specified":
            return format_html('<span style="color: #999;">Not specified</span>')
        return format_html('📍 {}', location)

    @admin.display(description='Favorite Games')
    def favorite_games_count(self, obj):
        count = obj.favorite_games.count()
        if count == 0:
            return format_html('<span style="color: #999;">0</span>')
        return str(count)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'favorite_games'
        ).select_related('country', 'region', 'city')
