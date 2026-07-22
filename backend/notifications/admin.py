from django.contrib import admin
from django.http import HttpRequest
from django.db.models import QuerySet

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin listing for notifications with a bulk 'mark as read' action."""

    list_display = ["user", "notification_type", "title", "is_read", "created_at"]
    list_filter = ["notification_type", "is_read", "created_at"]
    search_fields = ["user__username", "user__email", "title", "message"]
    autocomplete_fields = ["user"]
    readonly_fields = ["created_at"]
    actions = ["mark_as_read"]

    @admin.action(description="Mark selected notifications as read")
    def mark_as_read(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Bulk-flip the selected notifications to read and report the count."""
        updated = queryset.update(is_read=True)
        self.message_user(request, f"{updated} notification(s) marked as read.")
