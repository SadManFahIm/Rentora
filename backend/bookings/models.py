from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from rooms.models import Room


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="bookings")
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    check_in = models.DateField()
    check_out = models.DateField(null=True, blank=True)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    agreement_signed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    # Phase 15 — Monetization 2.0 attribution: the verified broker whose
    # referral code was used on this booking (earns a commission on approval).
    broker_referral = models.ForeignKey(
        "brokers.BrokerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals",
    )
    # The corporate account that booked this room in bulk (drives invoicing).
    corporate_account = models.ForeignKey(
        "corporate.CorporateAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )

    # Security deposit tracking. `security_deposit_amount` of 0 means no
    # deposit is required for this booking. Whether an unpaid deposit blocks
    # approval is a global, configurable business rule — see
    # `settings.REQUIRE_SECURITY_DEPOSIT_BEFORE_APPROVAL` — not hardcoded here.
    security_deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    security_deposit_paid = models.BooleanField(default=False)
    security_deposit_refunded = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tenant} -> {self.room} ({self.status})"


class Review(models.Model):
    class ModerationStatus(models.TextChoices):
        APPROVED = "approved", "Approved"
        PENDING = "pending", "Pending Moderation"
        REJECTED = "rejected", "Rejected"
        ESCALATED = "escalated", "Escalated"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    verified_stay = models.BooleanField(default=False)
    # Phase 17 — Fake-Review Detection (Stage 2 foundation)
    moderation_status = models.CharField(
        max_length=16,
        choices=ModerationStatus.choices,
        default=ModerationStatus.APPROVED,
        help_text="Moderation queue status. Default 'approved' preserves existing behaviour.",
    )
    trust_score = models.IntegerField(
        null=True,
        blank=True,
        help_text="Computed trust score 0-100. Null until scored by the review-trust detector.",
    )
    # Landlord reply (Phase 10 — Reviews v2): the room owner can answer a
    # review once; `reply` text + `replied_at` timestamp together mean "has
    # been answered".
    reply = models.TextField(blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    # Tenant photo proof — list of uploaded image URLs.
    photos = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["room", "user"], name="unique_review_per_user_per_room"
            ),
        ]

    def __str__(self):
        return f"{self.user} on {self.room} ({self.rating}*)"


def _recalculate_room_rating(room):
    agg = room.reviews.aggregate(avg=Avg("rating"), count=Count("id"))
    room.rating = agg["avg"] or 0
    room.total_reviews = agg["count"] or 0
    room.save(update_fields=["rating", "total_reviews"])


@receiver(post_save, sender=Review)
def update_room_rating_on_review_save(sender, instance, **kwargs):
    _recalculate_room_rating(instance.room)


@receiver(post_delete, sender=Review)
def update_room_rating_on_review_delete(sender, instance, **kwargs):
    _recalculate_room_rating(instance.room)
