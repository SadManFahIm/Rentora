from django.contrib import admin
from django.http import Http404
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from property_intelligence.engine import get_property_intelligence

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
        "tier",
        "is_featured",
        "rating",
        "owner",
        "pi_link",
    ]
    list_filter = [
        "area",
        "room_type",
        "is_available",
        "tier",
        "is_featured",
        "verified",
    ]
    search_fields = ["title", "description", "area"]
    autocomplete_fields = ["owner"]
    inlines = [RoomImageInline]

    # -- Property Intelligence (Phase 19.1) staff inspector -------------------

    def get_urls(self):
        urls = [
            path(
                "<path:object_id>/property-intelligence/",
                self.admin_site.admin_view(self.pi_inspect_view),
                name="rooms_room_property_intelligence",
            ),
        ]
        return urls + super().get_urls()

    @admin.display(description="Intelligence")
    def pi_link(self, obj):
        url = reverse(
            "admin:rooms_room_property_intelligence",
            args=[obj.pk],
            current_app=self.admin_site.name,
        )
        return format_html('<a href="{}">inspect</a>', url)

    def pi_inspect_view(self, request, object_id):
        """Read-only staff inspector for a room's Property Intelligence."""
        opts = self.model._meta
        room = self.get_object(request, object_id, from_field=None)
        if room is None:
            raise Http404(f"No {opts.verbose_name} matches the given query.")
        try:
            result = get_property_intelligence(room, include_internal=True)
        except Exception as exc:  # never render a 500 on the ops surface
            result = {
                "room_id": int(object_id),
                "score": None,
                "confidence": "none",
                "confidence_reasons": [f"{type(exc).__name__}: {exc}"],
                "breakdown": {},
                "strengths": [],
                "suggestions": [],
                "provenance": {},
                "_engine": {},
                "error": True,
            }
        context = {
            **self.admin_site.each_context(request),
            "title": f"Property Intelligence — {room.title}",
            "room": room,
            "pi": result,
            "engine_meta": result.get("_engine", {}),
            "opts": opts,
        }
        return render(request, "rooms/admin/property_intelligence.html", context)


@admin.register(RoomImage)
class RoomImageAdmin(admin.ModelAdmin):
    """Standalone admin for room images (also editable inline on Room)."""

    list_display = ["room", "is_primary", "created_at"]
    list_filter = ["is_primary"]
    search_fields = ["room__title"]
