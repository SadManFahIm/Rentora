from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the custom user model, extending Django's built-in UserAdmin
    with Rentora profile fields and rental-domain list/search controls."""

    fieldsets = DjangoUserAdmin.fieldsets + (
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
    )
    list_display = ("email", "name", "role", "nid_verified", "date_joined")
    list_filter = ("role", "nid_verified", "gender")
    search_fields = ("email", "first_name", "last_name", "phone")

    @admin.display(description="Name")
    def name(self, obj: User) -> str:
        """Full name for the changelist, falling back to the username."""
        return obj.get_full_name() or obj.username
