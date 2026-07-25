from django.contrib import admin
from django.utils.html import format_html

from .models import Invoice, Payment, PaymentAuditLog, PaymentSchedule

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


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "booking", "amount", "status", "period_start", "period_end", "created_at"]
    list_filter = ["status"]
    search_fields = ["invoice_number", "booking__tenant__username", "booking__room__title"]
    autocomplete_fields = ["booking", "payment"]
    readonly_fields = ["invoice_number", "created_at", "updated_at"]


@admin.register(PaymentSchedule)
class PaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ["booking", "due_date", "amount", "status", "payment"]
    list_filter = ["status"]
    autocomplete_fields = ["booking", "payment"]


@admin.register(PaymentAuditLog)
class PaymentAuditLogAdmin(admin.ModelAdmin):
    list_display = ["payment", "old_status", "new_status", "changed_by", "created_at"]
    list_filter = ["new_status", "changed_by"]
    search_fields = ["payment__transaction_id"]
    readonly_fields = ["payment", "old_status", "new_status", "changed_by", "metadata", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
