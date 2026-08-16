from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("event", "category", "user", "session_id", "path", "created_at")
    list_filter = ("event", "category", "created_at")
    search_fields = ("event", "path", "session_id")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
