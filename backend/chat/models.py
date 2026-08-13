from django.conf import settings
from django.db import models

from rooms.models import Room


class ChatRoom(models.Model):
    """A conversation between two (direct) or more (group) users.

    A room may optionally be tied to a :class:`rooms.models.Room` listing so a
    conversation about a specific rental keeps that context. Membership is
    modelled explicitly via :class:`ChatRoomMembership`.
    """

    class RoomType(models.TextChoices):
        DIRECT = "direct", "Direct"
        GROUP = "group", "Group"

    room_type = models.CharField(max_length=10, choices=RoomType.choices, default=RoomType.DIRECT)
    listing = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_rooms",
        help_text="Optional room listing this conversation is about.",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ChatRoomMembership",
        related_name="chat_rooms",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"ChatRoom #{self.pk} ({self.room_type})"


class ChatRoomMembership(models.Model):
    """Through model linking a user to a chat room.

    ``last_read_at`` powers read receipts / unread counts: everything created
    after this timestamp is unread for the member.
    """

    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("chat_room", "user")
        ordering = ["joined_at"]

    def __str__(self) -> str:
        return f"{self.user} in ChatRoom #{self.chat_room_id}"


class Message(models.Model):
    """A single message posted to a chat room."""

    class MessageType(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        FILE = "file", "File"
        SYSTEM = "system", "System"

    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    content = models.TextField()
    message_type = models.CharField(
        max_length=10, choices=MessageType.choices, default=MessageType.TEXT
    )
    file_url = models.URLField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["chat_room", "created_at"]),
        ]

    def __str__(self) -> str:
        preview = (self.content[:30] + "…") if len(self.content) > 30 else self.content
        return f"{self.sender}: {preview}"


class ChatSafetyEvent(models.Model):
    """One chat-message safety assessment (Phase 12.3 — chat safety engine).

    Created whenever the rule-based engine finds something worth remembering:
    a warning (medium), a flagged message (high) or a blocked message
    (critical). Only *metadata* is stored — the detector keys, the risk level,
    the outcome and short matched fragments — never the full conversation
    content, so sensitive chat text is not persisted beyond what the messages
    table already holds by design.

    ``outcome`` records what the engine did:

    - ``warned``  — delivered, recipient should be cautious (medium)
    - ``flagged`` — delivered but flagged for admin review (high)
    - ``blocked`` — replaced with a safety notice, raw content never stored

    A ``blocked`` event's ``message`` points at the placeholder message (the
    one that was actually stored), so the trail stays complete.
    """

    class RiskLevel(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Outcome(models.TextChoices):
        WARNED = "warned", "Warned"
        FLAGGED = "flagged", "Flagged"
        BLOCKED = "blocked", "Blocked"

    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="safety_events")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_safety_events",
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="safety_event",
    )
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices)
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    # Metadata only: [{"key", "label", "fragments": [snippet, ...]}, ...]
    detectors = models.JSONField(default=list, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sender", "created_at"]),
            models.Index(fields=["chat_room", "created_at"]),
            models.Index(fields=["outcome", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.risk_level}/{self.outcome} from {self.sender_id} in room {self.chat_room_id}"
