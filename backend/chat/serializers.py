from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from config.sanitizers import sanitize_text

from .models import ChatRoom, Message
from .presence import is_online

User = get_user_model()


class ChatUserSerializer(serializers.ModelSerializer):
    """Public-safe user subset embedded in chat payloads."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "avatar"]


class MessageSerializer(serializers.ModelSerializer):
    """Read representation of a message, with nested sender.

    ``status`` is derived, not stored: it's "delivered"/"read" per the other
    room member(s)' online state and ``last_read_at`` — see ``get_status``.
    """

    sender = ChatUserSerializer(read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "chat_room",
            "sender",
            "content",
            "message_type",
            "file_url",
            "is_read",
            "status",
            "created_at",
        ]
        read_only_fields = fields

    def get_status(self, obj: Message) -> str:
        """"read" once every other member has read past this message's
        timestamp; else "delivered" if any of them is currently online;
        else "sent". For a direct chat "every other member" is just the one
        other participant, so this reduces to the usual 1:1 semantics."""
        others = [m for m in obj.chat_room.memberships.all() if m.user_id != obj.sender_id]
        if not others:
            return "sent"
        if all(m.last_read_at is not None and m.last_read_at > obj.created_at for m in others):
            return "read"
        if any(is_online(m.user_id) for m in others):
            return "delivered"
        return "sent"


class MessageCreateSerializer(serializers.ModelSerializer):
    """Write serializer for sending a message. ``sender`` and ``chat_room`` are
    supplied by the view, never the client."""

    class Meta:
        model = Message
        fields = ["id", "content", "message_type", "file_url", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_content(self, value: str) -> str:
        """Strip HTML (stored-XSS guard) and require non-empty text."""
        cleaned = sanitize_text(value) or ""
        if not cleaned.strip():
            raise serializers.ValidationError("Message content cannot be empty.")
        return cleaned


class ChatRoomSerializer(serializers.ModelSerializer):
    """Chat room summary: the other participant (for direct rooms), the last
    message preview, and the requesting user's unread count."""

    other_participant = serializers.SerializerMethodField()
    is_other_user_online = serializers.SerializerMethodField()
    participants = ChatUserSerializer(source="members", many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    listing_title = serializers.CharField(source="listing.title", read_only=True, default=None)

    class Meta:
        model = ChatRoom
        fields = [
            "id",
            "room_type",
            "listing",
            "listing_title",
            "participants",
            "other_participant",
            "is_other_user_online",
            "last_message",
            "unread_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def _other_member(self, obj: ChatRoom):
        """For a direct chat, the member who isn't the requesting user.
        ``None`` for a group chat (or if the requester isn't a member)."""
        user = self._request_user()
        others = [m for m in obj.members.all() if m.pk != getattr(user, "pk", None)]
        return others[0] if others else None

    @extend_schema_field(ChatUserSerializer)
    def get_other_participant(self, obj: ChatRoom):
        other = self._other_member(obj)
        return ChatUserSerializer(other, context=self.context).data if other else None

    def get_is_other_user_online(self, obj: ChatRoom) -> bool | None:
        """``None`` when there's no single "other" participant (group chat)."""
        other = self._other_member(obj)
        return is_online(other.pk) if other else None

    @extend_schema_field(MessageSerializer)
    def get_last_message(self, obj: ChatRoom):
        last = obj.messages.order_by("-created_at").first()
        return MessageSerializer(last, context=self.context).data if last else None

    def get_unread_count(self, obj: ChatRoom) -> int:
        """Messages newer than the user's last_read_at, not sent by them."""
        user = self._request_user()
        if user is None or not user.is_authenticated:
            return 0
        membership = next(
            (m for m in obj.memberships.all() if m.user_id == user.pk), None
        )
        if membership is None:
            return 0
        qs = obj.messages.exclude(sender_id=user.pk)
        if membership.last_read_at is not None:
            qs = qs.filter(created_at__gt=membership.last_read_at)
        return qs.count()
