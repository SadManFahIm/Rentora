from django.contrib import admin
from django.utils.html import format_html

from .models import Booking, Review

# Badge colour per booking status, used by BookingAdmin.status_colored.
_STATUS_COLORS = {
    Booking.Status.PENDING: "#d97706",    # amber-600
    Booking.Status.APPROVED: "#16a34a",   # green-600
    Booking.Status.REJECTED: "#dc2626",   # red-600
    Booking.Status.CANCELLED: "#6b7280",  # gray-500
}


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Admin listing for bookings with a colour-coded status badge."""

    list_display = [
        "room",
        "tenant",
        "status_colored",
        "check_in",
        "monthly_rent",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["room__title", "tenant__username", "tenant__email"]
    autocomplete_fields = ["room", "tenant"]
    readonly_fields = ["created_at", "updated_at"]

    @admin.display(description="Status", ordering="status")
    def status_colored(self, obj: Booking) -> str:
        """Render the status as a coloured pill for quick scanning."""
        color = _STATUS_COLORS.get(obj.status, "#6b7280")
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>',
            color,
            obj.get_status_display(),
        )


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Admin listing for room reviews."""

    list_display = ["room", "user", "rating", "verified_stay", "created_at"]
    list_filter = ["rating", "verified_stay"]
    search_fields = ["room__title", "user__username", "comment"]
    autocomplete_fields = ["room", "user"]
    readonly_fields = ["created_at"]
