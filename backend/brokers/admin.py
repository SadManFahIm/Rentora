from django.contrib import admin

from .models import BrokerProfile, BrokerVerification


@admin.register(BrokerProfile)
class BrokerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "years_experience", "referral_code", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "referral_code")


@admin.register(BrokerVerification)
class BrokerVerificationAdmin(admin.ModelAdmin):
    list_display = ("profile", "status", "auto_screen_score", "auto_screen_result", "created_at")
    list_filter = ("status",)
    search_fields = ("profile__user__username",)
