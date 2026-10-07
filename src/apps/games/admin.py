from django.contrib import admin
from .models import Game


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):

    list_display = ['name', 'category',
                    'is_official', 'created_by', 'updated_at']
    list_filter = ['category', 'is_official', 'created_at']
    search_fields = ['name', 'slug']
    date_hierarchy = 'created_at'
    ordering = ['name']
    list_per_page = 50
    raw_id_fields = ['created_by']

    fieldsets = (
        ('Game Information', {
            'fields': ('name', 'category', 'description')
        }),
        ('Status', {
            'fields': ('is_official',)
        }),
        ('System (Auto-filled)', {
            'fields': ('slug', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'These fields are auto-generated and cannot be edited manually.'
        }),
    )

    readonly_fields = ['slug', 'created_by', 'created_at', 'updated_at']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')
