from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from config.sanitizers import sanitize_text

from .models import ChatRoom, Message

User = get_user_model()


class ChatUserSerializer(serializers.ModelSerializer):
    """Public-safe user subset embedded in chat payloads."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "avatar"]


class MessageSerializer(serializers.ModelSerializer):
    """Read representation of a message, with nested sender."""

    sender = ChatUserSerializer(read_only=True)

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
            "created_at",
        ]
        read_only_fields = fields


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
            "last_message",
            "unread_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    @extend_schema_field(ChatUserSerializer)
    def get_other_participant(self, obj: ChatRoom):
        """For a direct chat, the member who isn't the requesting user."""
        user = self._request_user()
        others = [m for m in obj.members.all() if m.pk != getattr(user, "pk", None)]
        if not others:
            return None
        return ChatUserSerializer(others[0], context=self.context).data

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
