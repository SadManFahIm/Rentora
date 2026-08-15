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
    # Message editing (Tier-1 quick win): the sender may edit their own text
    # message; ``edited_at`` distinguishes an edit from the original and is
    # surfaced to both parties ("edited" chip). Never null for a deleted
    # message (deletion is a soft-delete that also stamps the time).
    edited_at = models.DateTimeField(null=True, blank=True)
    # Soft delete: the row stays so the conversation thread keeps its shape,
    # but the content is replaced with a generic notice and the message is
    # excluded from search results. The original content is never recovered
    # through the API (it's gone from this row once replaced).
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["chat_room", "created_at"]),
            models.Index(fields=["chat_room", "is_deleted"]),
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


class UserBlock(models.Model):
    """A user blocking another user (Phase 12.4).

    Blocking is enforced for *both* directions: if either member of a pair
    blocks the other, neither can message the other (or start a new direct
    chat). The blocker can unblock at any time — unblocking is one-way, so a
    blocked user cannot re-open the channel themselves.
    """

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_users",
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("blocker", "blocked")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.blocker_id} blocked {self.blocked_id}"


class Report(models.Model):
    """A user's report of another user and/or a specific message (Phase 12.4).

    The moderation queue admins review lives here: a report carries its
    category, the reporter's description, and — when a specific message was
    flagged — a reference to it (e.g. a suspicious payment request). Admins
    act on it (dismiss / warn / suspend / escalate); every action is written
    to the append-only audit log (``report.*``) and the reporter is notified
    of the outcome.
    """

    class Category(models.TextChoices):
        SCAM = "scam", "Scam"
        HARASSMENT = "harassment", "Harassment"
        FAKE_LISTING = "fake_listing", "Fake listing"
        PAYMENT_FRAUD = "payment_fraud", "Payment fraud"
        IMPERSONATION = "impersonation", "Impersonation"
        SPAM = "spam", "Spam"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under review"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"
        ESCALATED = "escalated", "Escalated"

    class Action(models.TextChoices):
        NONE = "", "—"
        WARN = "warn", "Warned"
        SUSPEND = "suspend", "Suspended"
        ESCALATE = "escalate", "Escalated"
        DISMISS = "dismiss", "Dismissed"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_made",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_received",
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
        help_text="The specific message being reported (e.g. a suspicious payment request).",
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    action_taken = models.CharField(max_length=10, choices=Action.choices, default=Action.NONE)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["target_user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_category_display()} by {self.reporter_id} → {self.target_user_id} ({self.status})"
