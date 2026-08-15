from django.conf import settings
from django.db import models


class Dispute(models.Model):
    """A structured dispute around a booking (Phase 12 — dispute resolution).

    Either party of an approved booking may open one dispute; the other party
    responds with evidence, an admin reviews, and the dispute resolves with a
    decision (including, where relevant, what happens to the security
    deposit). Every admin decision is audited (``dispute.*``) and both
    parties are notified of state changes.

    Deposit wording stays honest: we never claim \"escrow\". The platform
    tracks whether a deposit is paid and whether it has been released/refunded
    (``Booking.security_deposit_refunded``) — a resolution decision marks the
    deposit as no longer held and records *who* received it.
    """

    class Category(models.TextChoices):
        DEPOSIT = "deposit", "Security deposit"
        PROPERTY_CONDITION = "property_condition", "Property condition"
        BOOKING_CANCELLATION = "booking_cancellation", "Booking cancellation"
        MISREPRESENTATION = "misrepresentation", "Misrepresentation"
        PAYMENT = "payment", "Payment"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under review"
        WAITING_FOR_TENANT = "waiting_for_tenant", "Waiting for tenant"
        WAITING_FOR_LANDLORD = "waiting_for_landlord", "Waiting for landlord"
        ESCALATED = "escalated", "Escalated"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    class Decision(models.TextChoices):
        NONE = "none", "No decision"
        RELEASE_TO_LANDLORD = "release_to_landlord", "Deposit released to landlord"
        REFUND_TO_TENANT = "refund_to_tenant", "Deposit refunded to tenant"
        PARTIAL_RESOLUTION = "partial", "Partial resolution"

    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.CASCADE, related_name="disputes"
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="disputes_opened"
    )
    category = models.CharField(max_length=32, choices=Category.choices)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    # ---- Resolution state (filled by an admin) ----
    decision = models.CharField(max_length=24, choices=Decision.choices, default=Decision.NONE)
    decision_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    resolution = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disputes_resolved",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["booking", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"#{self.pk} {self.get_category_display()} on booking {self.booking_id} ({self.status})"
        )


class DisputeEvidence(models.Model):
    """One piece of evidence in a dispute (Phase 12 — evidence system).

    May be a text statement, an uploaded document/photo, or a chat context
    string. Access is strictly limited to the dispute's two parties and
    admins — never exposed publicly.
    """

    class Kind(models.TextChoices):
        TEXT = "text", "Text statement"
        PHOTO = "photo", "Photo"
        DOCUMENT = "document", "Document"

    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="evidence")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dispute_evidence"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEXT)
    content = models.TextField(blank=True)
    file = models.FileField(upload_to="disputes/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} by {self.uploaded_by_id} on dispute {self.dispute_id}"
