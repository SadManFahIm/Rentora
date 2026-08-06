from django.contrib import admin

from .models import RoommateMatchRequest, RoommateProfile


@admin.register(RoommateProfile)
class RoommateProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "preferred_area", "room_type_pref", "budget_min", "budget_max", "is_looking"]
    list_filter = ["preferred_area", "room_type_pref", "is_looking"]
    search_fields = ["user__username", "user__first_name", "user__last_name", "occupation"]


@admin.register(RoommateMatchRequest)
class RoommateMatchRequestAdmin(admin.ModelAdmin):
    list_display = ["sender", "receiver", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["sender__username", "receiver__username"]
