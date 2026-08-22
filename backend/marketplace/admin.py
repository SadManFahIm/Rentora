from django.contrib import admin

from .models import AddonOrder, AddonProvider, AddonService


@admin.register(AddonProvider)
class AddonProviderAdmin(admin.ModelAdmin):
    list_display = ("business_name", "user", "status", "commission_rate")
    list_filter = ("status",)
    search_fields = ("business_name", "user__username", "user__email")


@admin.register(AddonService)
class AddonServiceAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "category", "price", "is_active", "rating_avg")
    list_filter = ("category", "is_active")
    search_fields = ("title", "provider__business_name")


@admin.register(AddonOrder)
class AddonOrderAdmin(admin.ModelAdmin):
    list_display = ("service", "tenant", "quantity", "total", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("tenant__username", "tenant__email")
