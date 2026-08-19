from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

from config.sanitizers import sanitize_text

from .models import ChatRoom, ChatSafetyEvent, Message, Report
from .presence import is_online

User = get_user_model()


class ChatUserSerializer(serializers.ModelSerializer):
    """Public-safe user subset embedded in chat payloads.

    ``nid_verified`` (landlord) and ``tenant_verified`` (tenant) are exposed so
    chat participants can show the right trust badge next to the other person's
    name — same trust signal as rooms. ``trust_signals`` (Tier 3) adds the
    behavioral side (completed bookings) so a landlord can see at a glance
    that the person they're talking to has actually completed stays.
    """

    trust_signals = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "avatar",
            "nid_verified",
            "tenant_verified",
            "trust_signals",
        ]

    @extend_schema_field(
        inline_serializer(
            "ChatUserTrustSignals",
            fields={
                "tenant_verified": serializers.BooleanField(read_only=True),
                "nid_verified": serializers.BooleanField(read_only=True),
                "completed_bookings": serializers.IntegerField(read_only=True),
                "profile_complete": serializers.BooleanField(read_only=True),
            },
        )
    )
    def get_trust_signals(self, obj):
        from users.trust import trust_signals

        return trust_signals(obj)


class MessageSerializer(serializers.ModelSerializer):
    """Read representation of a message, with nested sender.

    ``status`` is derived, not stored: it's "delivered"/"read" per the other
    room member(s)' online state and ``last_read_at`` — see ``get_status``.
    ``is_deleted``/``edited_at`` surface the edit/delete lifecycle (Tier-1
    quick win) so clients can render "deleted" styling and an "edited" hint.
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
            "is_deleted",
            "edited_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_status(self, obj: Message) -> str:
        """ "read" once every other member has read past this message's
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


class MessageEditSerializer(serializers.ModelSerializer):
    """Write serializer for editing a message: only the new ``content``.

    Same sanitization as sending — HTML is stripped (stored-XSS guard) and
    empty edits are rejected. ``sender``/``chat_room`` come from the view.
    """

    class Meta:
        model = Message
        fields = ["content"]

    def validate_content(self, value: str) -> str:
        return MessageCreateSerializer().validate_content(value)


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
        membership = next((m for m in obj.memberships.all() if m.user_id == user.pk), None)
        if membership is None:
            return 0
        qs = obj.messages.exclude(sender_id=user.pk)
        if membership.last_read_at is not None:
            qs = qs.filter(created_at__gt=membership.last_read_at)
        return qs.count()


class ChatSafetyEventSerializer(serializers.ModelSerializer):
    """Admin-only view of one chat-safety event — metadata only.

    Deliberately excludes the message content: admins see who, where, what
    tripped (detector keys + risk) and what the engine did, but not the
    conversation text.
    """

    sender_username = serializers.CharField(source="sender.username", read_only=True)
    sender_name = serializers.SerializerMethodField()
    risk_level_display = serializers.CharField(source="get_risk_level_display", read_only=True)
    outcome_display = serializers.CharField(source="get_outcome_display", read_only=True)

    class Meta:
        model = ChatSafetyEvent
        fields = [
            "id",
            "chat_room",
            "sender_username",
            "sender_name",
            "risk_level",
            "risk_level_display",
            "outcome",
            "outcome_display",
            "detectors",
            "detail",
            "created_at",
        ]
        read_only_fields = fields

    def get_sender_name(self, obj: ChatSafetyEvent) -> str:
        return obj.sender.get_full_name() or obj.sender.username


class ReportCreateSerializer(serializers.Serializer):
    """Input for reporting a user and/or a specific message (Phase 12.4).

    ``message_id`` is optional — a report can be about a user's general
    behaviour (harassment, impersonation) or a concrete message (payment
    fraud / suspicious payment request).
    """

    target_user_id = serializers.IntegerField()
    message_id = serializers.IntegerField(required=False, allow_null=True)
    category = serializers.ChoiceField(choices=Report.Category.choices)
    description = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=2000
    )

    def validate_target_user_id(self, value):
        if value == self.context["request"].user.pk:
            raise serializers.ValidationError("You cannot report yourself.")
        return value


class ReportSerializer(serializers.ModelSerializer):
    """One report in the admin moderation queue."""

    reporter_username = serializers.CharField(source="reporter.username", read_only=True)
    reporter_name = serializers.SerializerMethodField()
    target_username = serializers.CharField(source="target_user.username", read_only=True)
    target_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    action_taken_display = serializers.CharField(source="get_action_taken_display", read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            "reporter_username",
            "reporter_name",
            "target_user",
            "target_username",
            "target_name",
            "message",
            "category",
            "category_display",
            "description",
            "status",
            "status_display",
            "action_taken",
            "action_taken_display",
            "admin_note",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = fields

    def get_reporter_name(self, obj: Report) -> str:
        return obj.reporter.get_full_name() or obj.reporter.username

    def get_target_name(self, obj: Report) -> str:
        return obj.target_user.get_full_name() or obj.target_user.username


class ReportActionSerializer(serializers.Serializer):
    """Admin decision on a report: dismiss | warn | suspend | escalate."""

    action = serializers.ChoiceField(choices=["dismiss", "warn", "suspend", "escalate"])
    note = serializers.CharField(required=False, allow_blank=True, default="")


class TranslateRequestSerializer(serializers.Serializer):
    """Request payload for the chat translation endpoint (Phase 15 — B1)."""

    text = serializers.CharField(min_length=1, max_length=4000)
    target = serializers.ChoiceField(choices=["en", "bn"])
