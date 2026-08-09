from django.contrib import admin

from .models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ["created_at", "action", "actor", "target_type", "target_id"]
    list_filter = ["action"]
    search_fields = ["actor__username", "target_id", "action"]
    readonly_fields = [
        "actor",
        "action",
        "target_type",
        "target_id",
        "detail",
        "ip_address",
        "created_at",
    ]
    date_hierarchy = "created_at"

    # Append-only: never let entries be edited or deleted through the admin.
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
