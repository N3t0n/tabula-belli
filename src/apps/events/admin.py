from django.contrib import admin
from .models import Event, EventRegistration
from .forms import EventAdminForm


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm
    list_display = ("title", "event_type", "game", "status",
                    "start_at", "location_display")
    list_filter = (
        "event_type",
        "status",
        ("country", admin.RelatedOnlyFieldListFilter),
        ("region", admin.RelatedOnlyFieldListFilter),
        ("city", admin.RelatedOnlyFieldListFilter),
        ("game", admin.RelatedOnlyFieldListFilter),
        ("start_at", admin.DateFieldListFilter)
    )
    search_fields = ("title", "slug")
    date_hierarchy = "start_at"
    ordering = ("-start_at",)
    list_per_page = 25
    list_select_related = ("country", "region", "city", "game", "organizer")

    fieldsets = (
        ("Basic Info", {"fields": ("title", "slug",
         "event_type", "status", "description")}),
        ("Game & Organizer", {"fields": ("game", "organizer")}),
        ("Location", {"fields": ("country", "region",
         "city", "location_name", "location_address")}),
        ("Dates", {"fields": (("start_at", "end_at"),
                              ("registration_opens_at", "registration_closes_at"))}),
        ("Details", {"fields": ("capacity", "price")}),
        ("System", {"fields": ("created_at", "updated_at"),
         "classes": ("collapse",)}),
    )
    prepopulated_fields = {}  # Slug auto-generated in save(), not from JS
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("game", "organizer")

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)

        if obj is None:
            fieldsets = list(fieldsets)
            basic_info_section = fieldsets[0]

            original_fields = basic_info_section[1]["fields"]
            filtered_fields = tuple(f for f in original_fields if f != "slug")

            fieldsets[0] = (
                basic_info_section[0],
                {"fields": filtered_fields}
            )

        return fieldsets

    @admin.display(description="Location")
    def location_display(self, obj):
        return obj.get_location_display()


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "player_username",
        "event_title",
        "status",
        "created_at",
        "cancelled_at"
    )
    list_filter = (
        "status",
        ("created_at", admin.DateFieldListFilter),
        ("event", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        "player__username",
        "player__email",
        "event__title",
        "event__slug"
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 25
    list_select_related = ("event", "player")

    fieldsets = (
        ("Registration Info", {
            "fields": ("event", "player", "status")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at", "cancelled_at"),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("created_at", "updated_at", "cancelled_at")
    raw_id_fields = ("event", "player")

    @admin.display(description="Player", ordering="player__username")
    def player_username(self, obj):
        return obj.player_display

    @admin.display(description="Event", ordering="event__title")
    def event_title(self, obj):
        return obj.event.title

    actions = ["mark_as_cancelled"]

    @admin.action(description="Mark selected as cancelled")
    def mark_as_cancelled(self, request, queryset):
        count = 0
        for registration in queryset:
            if registration.status != EventRegistration.Status.CANCELLED:
                registration.cancel()
                count += 1
        self.message_user(request, f"{count} registration(s) cancelled.")
