from django.contrib import admin

from .models import Booking, Review


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["room", "tenant", "status", "check_in", "check_out", "monthly_rent", "agreement_signed"]
    list_filter = ["status", "agreement_signed"]
    search_fields = ["room__title", "tenant__username"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["room", "user", "rating", "verified_stay", "created_at"]
    list_filter = ["rating", "verified_stay"]
    search_fields = ["room__title", "user__username", "comment"]
