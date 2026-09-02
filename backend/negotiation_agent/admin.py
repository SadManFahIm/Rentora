"""AI Negotiation Agent — admin (Phase 19.4).

Read-mostly: audits should inspect; participants act through the app. We never
allow editing negotiation state by hand — but terminal fixes (accidental bad
rows) live with a superuser, so delete/edit is left to the privileged admin.
"""

from django.contrib import admin

from .models import Negotiation, NegotiationEvent, NegotiationOffer


class NegotiationOfferInline(admin.TabularInline):
    model = NegotiationOffer
    extra = 0
    readonly_fields = [
        "offer_key",
        "sender",
        "kind",
        "amount",
        "message",
        "meta",
        "status",
        "expires_at",
        "created_at",
    ]
    can_delete = False
    max_num = 20


class NegotiationEventInline(admin.TabularInline):
    model = NegotiationEvent
    extra = 0
    readonly_fields = ["event_type", "actor", "detail", "created_at"]
    can_delete = False
    max_num = 50


@admin.register(Negotiation)
class NegotiationAdmin(admin.ModelAdmin):
    list_display = [
        "negotiation_key",
        "room",
        "tenant",
        "landlord",
        "status",
        "created_at",
        "updated_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = [
        "negotiation_key",
        "room__title",
        "tenant__username",
        "landlord__username",
    ]
    readonly_fields = [
        "negotiation_key",
        "created_at",
        "updated_at",
        "tenant_constraints",
        "landlord_constraints",
    ]
    inlines = [NegotiationOfferInline, NegotiationEventInline]

    def has_add_permission(self, request):
        return False


@admin.register(NegotiationOffer)
class NegotiationOfferAdmin(admin.ModelAdmin):
    list_display = ["offer_key", "negotiation", "sender", "kind", "amount", "status", "created_at"]
    list_filter = ["status", "kind"]
    search_fields = ["offer_key", "sender__username", "negotiation__room__title"]
    readonly_fields = ["offer_key", "created_at", "updated_at", "meta", "chat_message"]
