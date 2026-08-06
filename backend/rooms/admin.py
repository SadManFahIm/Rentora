from django.contrib import admin

from .models import Room, RoomImage


class RoomImageInline(admin.TabularInline):
    """Inline editor for a room's gallery images on the Room admin page."""

    model = RoomImage
    extra = 0


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    """Admin listing for rooms, with a nested image editor."""

    list_display = [
        "title",
        "area",
        "room_type",
        "price",
        "is_available",
        "is_featured",
        "rating",
        "owner",
    ]
    list_filter = [
        "area",
        "room_type",
        "is_available",
        "is_featured",
        "verified",
    ]
    search_fields = ["title", "description", "area"]
    autocomplete_fields = ["owner"]
    inlines = [RoomImageInline]


@admin.register(RoomImage)
class RoomImageAdmin(admin.ModelAdmin):
    """Standalone admin for room images (also editable inline on Room)."""

    list_display = ["room", "is_primary", "created_at"]
    list_filter = ["is_primary"]
    search_fields = ["room__title"]
