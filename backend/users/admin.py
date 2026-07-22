from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
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
    list_display = ("username", "email", "role", "nid_verified", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("role", "nid_verified")
