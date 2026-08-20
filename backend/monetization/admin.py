from django.contrib import admin

from .models import Commission, CommissionRule, Payout, RevenueLedgerEntry


@admin.register(CommissionRule)
class CommissionRuleAdmin(admin.ModelAdmin):
    list_display = ("scope", "rate", "active")


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ("kind", "recipient", "amount", "rate", "status", "source_type", "source_id")
    list_filter = ("kind", "status")
    search_fields = ("recipient__username", "recipient__email", "idempotency_key")


@admin.register(RevenueLedgerEntry)
class RevenueLedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "entry_type",
        "scope",
        "gross_amount",
        "platform_amount",
        "partner_amount",
        "created_at",
    )
    list_filter = ("entry_type", "scope")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("recipient", "amount", "method", "status", "created_at")
    list_filter = ("status", "method")
    search_fields = ("recipient__username", "recipient__email")
