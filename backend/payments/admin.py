from django.contrib import admin
from django.utils.html import format_html

from .models import Payment

STATUS_COLORS = {
    Payment.Status.INITIATED: "#6b7280",
    Payment.Status.PENDING: "#d97706",
    Payment.Status.SUCCESS: "#16a34a",
    Payment.Status.FAILED: "#dc2626",
    Payment.Status.CANCELLED: "#6b7280",
    Payment.Status.REFUNDED: "#2563eb",
}


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "transaction_id",
        "booking",
        "user",
        "amount",
        "payment_method",
        "payment_type",
        "colored_status",
        "created_at",
    ]
    list_filter = ["status", "payment_method", "payment_type"]
    search_fields = ["transaction_id", "gateway_transaction_id", "user__username", "user__email"]
    autocomplete_fields = ["booking", "user"]
    readonly_fields = ["gateway_response", "transaction_id", "created_at", "updated_at"]

    @admin.display(description="Status")
    def colored_status(self, obj):
        color = STATUS_COLORS.get(obj.status, "#6b7280")
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            obj.get_status_display(),
        )
