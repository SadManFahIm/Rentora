from django.contrib import admin

from .models import ChatRoom, ChatRoomMembership, Message


class ChatRoomMembershipInline(admin.TabularInline):
    """Edit a chat room's members inline on the ChatRoom page."""

    model = ChatRoomMembership
    extra = 0
    autocomplete_fields = ["user"]
    readonly_fields = ["joined_at"]


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    """Admin listing for chat rooms."""

    list_display = ["id", "room_type", "listing", "created_at", "updated_at"]
    list_filter = ["room_type", "created_at"]
    search_fields = ["listing__title", "memberships__user__username"]
    autocomplete_fields = ["listing"]
    inlines = [ChatRoomMembershipInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Admin listing for chat messages."""

    list_display = ["id", "chat_room", "sender", "message_type", "is_read", "created_at"]
    list_filter = ["message_type", "is_read", "created_at"]
    search_fields = ["content", "sender__username"]
    autocomplete_fields = ["chat_room", "sender"]
    readonly_fields = ["created_at"]
