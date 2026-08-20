from django.contrib import admin

from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "price", "billing_cycle", "active")
    list_filter = ("billing_cycle", "active")
    search_fields = ("code", "name")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "current_period_start", "current_period_end")
    list_filter = ("status", "plan")
    search_fields = ("user__username", "user__email")
