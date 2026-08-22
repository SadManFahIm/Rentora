from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import LivenessChallenge, LivenessConsent, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the custom user model, extending Django's built-in UserAdmin
    with Rentora profile fields and rental-domain list/search controls."""

    fieldsets = [
        *DjangoUserAdmin.fieldsets,
        (
            "Rentora profile",
            {
                "fields": (
                    "phone",
                    "avatar",
                    "role",
                    "gender",
                    "nid_verified",
                    "bio",
                    "date_of_birth",
                )
            },
        ),
    ]
    list_display = ("email", "name", "role", "nid_verified", "date_joined")
    list_filter = ("role", "nid_verified", "gender")
    search_fields = ("email", "first_name", "last_name", "phone")

    @admin.display(description="Name")
    def name(self, obj: User) -> str:
        """Full name for the changelist, falling back to the username."""
        return obj.get_full_name() or obj.username


@admin.register(LivenessChallenge)
class LivenessChallengeAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "challenge_type", "provider_name", "created_at")
    list_filter = ("status", "challenge_type")
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user",)


@admin.register(LivenessConsent)
class LivenessConsentAdmin(admin.ModelAdmin):
    list_display = ("user", "consent_type", "granted", "granted_at", "revoked_at")
    list_filter = ("consent_type", "granted")
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user",)
