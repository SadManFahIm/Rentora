from django.contrib import admin

from .models import Room, RoomImage


class RoomImageInline(admin.TabularInline):
    model = RoomImage
    extra = 0


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["title", "area", "room_type", "price", "owner", "is_available", "is_featured", "verified"]
    list_filter = ["area", "room_type", "gender_preference", "is_available", "is_featured", "verified"]
    search_fields = ["title", "description", "area"]
    inlines = [RoomImageInline]


@admin.register(RoomImage)
class RoomImageAdmin(admin.ModelAdmin):
    list_display = ["room", "is_primary", "created_at"]
    list_filter = ["is_primary"]
