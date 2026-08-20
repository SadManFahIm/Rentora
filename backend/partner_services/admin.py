from django.contrib import admin

from .models import InsuranceProduct, InsuranceQuote, Partner


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "enabled")
    list_filter = ("kind", "enabled")


@admin.register(InsuranceProduct)
class InsuranceProductAdmin(admin.ModelAdmin):
    list_display = ("name", "partner", "price_monthly", "deductible", "is_active")
    list_filter = ("is_active", "partner")


@admin.register(InsuranceQuote)
class InsuranceQuoteAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "price", "status", "created_at")
    list_filter = ("status",)
