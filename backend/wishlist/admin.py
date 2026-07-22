from django.contrib import admin

from .models import Wishlist


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    """Admin listing for saved-room entries."""

    list_display = ["user", "room", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__username", "user__email", "room__title"]
    autocomplete_fields = ["user", "room"]
    readonly_fields = ["created_at"]
