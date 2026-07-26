from django.contrib import admin

from .models import UserActivity


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ["user", "activity_type", "room", "weight", "created_at"]
    list_filter = ["activity_type", "created_at"]
    search_fields = ["user__username", "user__email", "room__title"]
    autocomplete_fields = ["user", "room"]
    readonly_fields = ["created_at"]
