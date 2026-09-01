"""AI Negotiation Agent domain model — Phase 19.4.

The negotiation state machine (9 states) and the offer lifecycle are the
authoritative, server-side record of a price discussion between a tenant and
the listing landlord. The LLM can only *draft* and *propose* — every actual
state change is driven through the SDK's human-approval proposal pipeline and
applied here exactly once.

States (spec §12): INITIATED, ACTIVE, OFFER_PENDING, COUNTER_OFFER_PENDING,
ACCEPTED, REJECTED, EXPIRED, CANCELLED, CLOSED.
Offers: DRAFT → SENT → ACCEPTED | REJECTED | EXPIRED | WITHDRAWN.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import constants as C


class NegotiationStatus(models.TextChoices):
    INITIATED = "initiated", _("Initiated")
    ACTIVE = "active", _("Active")
    OFFER_PENDING = "offer_pending", _("Offer pending")
    COUNTER_OFFER_PENDING = "counter_offer_pending", _("Counter offer pending")
    ACCEPTED = "accepted", _("Accepted")
    REJECTED = "rejected", _("Rejected")
    EXPIRED = "expired", _("Expired")
    CANCELLED = "cancelled", _("Cancelled")
    CLOSED = "closed", _("Closed")


TERMINAL_STATES = {
    NegotiationStatus.ACCEPTED,
    NegotiationStatus.REJECTED,
    NegotiationStatus.EXPIRED,
    NegotiationStatus.CANCELLED,
    NegotiationStatus.CLOSED,
}

OPEN_STATES = {
    NegotiationStatus.INITIATED,
    NegotiationStatus.ACTIVE,
    NegotiationStatus.OFFER_PENDING,
    NegotiationStatus.COUNTER_OFFER_PENDING,
}

# Legal moves (source -> allowed targets).
TRANSITIONS: dict[str, set[str]] = {
    NegotiationStatus.INITIATED: {
        NegotiationStatus.ACTIVE,
        NegotiationStatus.OFFER_PENDING,
        NegotiationStatus.COUNTER_OFFER_PENDING,
        NegotiationStatus.ACCEPTED,
        NegotiationStatus.REJECTED,
        NegotiationStatus.CANCELLED,
        NegotiationStatus.EXPIRED,
        NegotiationStatus.CLOSED,
    },
    NegotiationStatus.ACTIVE: {
        NegotiationStatus.OFFER_PENDING,
        NegotiationStatus.COUNTER_OFFER_PENDING,
        NegotiationStatus.ACCEPTED,
        NegotiationStatus.REJECTED,
        NegotiationStatus.CANCELLED,
        NegotiationStatus.EXPIRED,
        NegotiationStatus.CLOSED,
    },
    NegotiationStatus.OFFER_PENDING: {
        NegotiationStatus.COUNTER_OFFER_PENDING,
        NegotiationStatus.OFFER_PENDING,
        NegotiationStatus.ACTIVE,
        NegotiationStatus.ACCEPTED,
        NegotiationStatus.REJECTED,
        NegotiationStatus.CANCELLED,
        NegotiationStatus.EXPIRED,
        NegotiationStatus.CLOSED,
    },
    NegotiationStatus.COUNTER_OFFER_PENDING: {
        NegotiationStatus.OFFER_PENDING,
        NegotiationStatus.COUNTER_OFFER_PENDING,
        NegotiationStatus.ACTIVE,
        NegotiationStatus.ACCEPTED,
        NegotiationStatus.REJECTED,
        NegotiationStatus.CANCELLED,
        NegotiationStatus.EXPIRED,
        NegotiationStatus.CLOSED,
    },
    NegotiationStatus.ACCEPTED: {NegotiationStatus.CLOSED},
    NegotiationStatus.REJECTED: set(),
    NegotiationStatus.EXPIRED: set(),
    NegotiationStatus.CANCELLED: set(),
    NegotiationStatus.CLOSED: set(),
}


class OfferStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    SENT = "sent", _("Sent")
    ACCEPTED = "accepted", _("Accepted")
    REJECTED = "rejected", _("Rejected")
    EXPIRED = "expired", _("Expired")
    WITHDRAWN = "withdrawn", _("Withdrawn")


class OfferKind(models.TextChoices):
    OFFER = "offer", _("Offer")
    COUNTER = "counter", _("Counter offer")


class Negotiation(models.Model):
    """A rent negotiation between a tenant and a listing's landlord."""

    negotiation_key = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )
    room = models.ForeignKey("rooms.Room", on_delete=models.CASCADE, related_name="negotiations")
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="negotiations_as_tenant",
    )
    landlord = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="negotiations_as_landlord",
    )
    status = models.CharField(
        max_length=24,
        choices=NegotiationStatus.choices,
        default=NegotiationStatus.INITIATED,
        db_index=True,
    )
    # One agent chat per party, so both sides can draft with the AI assistant.
    tenant_conversation = models.OneToOneField(
        "agents.AgentConversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="negotiation_as_tenant",
    )
    landlord_conversation = models.OneToOneField(
        "agents.AgentConversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="negotiation_as_landlord",
    )
    # The real tenant<->landlord chat thread used to deliver sent offers.
    chat_room = models.ForeignKey(
        "chat.ChatRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="negotiations",
    )
    # Each party's explicit boundaries — private per party; an agent reading
    # context only ever sees the *acting* party's own bounds.
    tenant_constraints = models.JSONField(default=dict, blank=True)
    landlord_constraints = models.JSONField(default=dict, blank=True)

    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["room", "tenant", "landlord"],
                name="uniq_negotiation_per_room_pair",
            )
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
        ]
        verbose_name = _("Negotiation")
        verbose_name_plural = _("Negotiations")

    def __str__(self):
        return f"neg {self.negotiation_key} [{self.status}] room#{self.room_id}"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def party_constraints(self, user) -> dict:
        """The acting party's own explicit boundaries (empty when not set).
        NEVER the other party's constraints."""
        if user is not None and self.tenant_id == getattr(user, "pk", None):
            return dict(self.tenant_constraints or {})
        if user is not None and self.landlord_id == getattr(user, "pk", None):
            return dict(self.landlord_constraints or {})
        return {}

    def counterparty(self, user):
        if user is None:
            return None
        if self.tenant_id == getattr(user, "pk", None):
            return self.landlord
        if self.landlord_id == getattr(user, "pk", None):
            return self.tenant
        return None

    def role_of(self, user) -> str:
        if user is None:
            return ""
        if self.tenant_id == getattr(user, "pk", None):
            return "tenant"
        if self.landlord_id == getattr(user, "pk", None):
            return "landlord"
        return ""

    def conversation_for(self, user):
        if user is None:
            return None
        if self.tenant_id == getattr(user, "pk", None):
            return self.tenant_conversation_id
        if self.landlord_id == getattr(user, "pk", None):
            return self.landlord_conversation_id
        return None

    def latest_outstanding_offer(self):
        """Newest SENT (non-terminal) offer, or None."""
        return self.offers.filter(status=OfferStatus.SENT).order_by("-created_at").first()


class NegotiationOffer(models.Model):
    """One concrete monetary proposal within a negotiation.

    Almost every offer starts as a DRAFT produced by ``negotiation.create_offer``
    / ``negotiation.counter_offer`` (human approval), then moves to SENT only
    after a second explicit approval on ``message.send`` — the "write" is never
    the "send". ``expires_at`` gives the counterparty a bounded window; the
    daily expiry task enforces it and replay protection rejects any stale use.
    """

    offer_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    negotiation = models.ForeignKey(Negotiation, on_delete=models.CASCADE, related_name="offers")
    proposal = models.ForeignKey(
        "agents.AgentProposal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="negotiation_offer",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="negotiation_offers_sent",
    )
    kind = models.CharField(max_length=16, choices=OfferKind.choices, default=OfferKind.OFFER)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    message = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=OfferStatus.choices, default=OfferStatus.DRAFT, db_index=True
    )
    chat_message = models.ForeignKey(
        "chat.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="negotiation_offer",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["negotiation", "status", "-created_at"]),
            models.Index(fields=["status", "expires_at"]),
        ]
        verbose_name = _("Negotiation offer")
        verbose_name_plural = _("Negotiation offers")

    def __str__(self):
        return f"offer {self.offer_key} {self.amount} [{self.status}]"

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at


class NegotiationEvent(models.Model):
    """Immutable, audit-friendly timeline of a negotiation."""

    negotiation = models.ForeignKey(Negotiation, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=32, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["negotiation", "-created_at"])]
        verbose_name = _("Negotiation event")

    def __str__(self):
        return f"neg#{self.negotiation_id} {self.event_type}"


def record_event(negotiation, event_type, *, actor=None, **detail) -> NegotiationEvent:
    """Append one timeline row (never raises)."""
    from contextlib import suppress

    with suppress(Exception):
        return NegotiationEvent.objects.create(
            negotiation=negotiation,
            event_type=event_type,
            actor=actor,
            detail=detail or {},
        )
    return None


def transition_negotiation(
    negotiation: Negotiation,
    target: str,
    *,
    actor=None,
    event: str = "",
    **detail,
) -> bool:
    """Move ``negotiation`` to ``target`` iff legal (server-own state machine).

    Returns True when the state actually changed; False on a no-op or an
    illegal move (the caller must never assume success). ``record_event`` is
    guarded so auditing can never break a state transition.
    """
    previous = negotiation.status
    if previous == target:
        return False
    allowed = TRANSITIONS.get(previous, set())
    if target not in allowed:
        return False
    negotiation.status = target
    negotiation.save(update_fields=["status", "updated_at"])
    if event:
        record_event(negotiation, event, actor=actor, previous=previous, **detail)
    return True


# Re-exported so services/tests import one place for the configurable knobs.
def settings() -> C.NegotiationSettings:
    return C.NegotiationSettings()
