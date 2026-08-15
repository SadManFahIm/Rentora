from django.conf import settings
from django.db import models


class ModerationStatus(models.TextChoices):
    """Shared moderation lifecycle.

    - ``pending``  — needs an admin decision before it is public
    - ``approved`` — reviewed and published
    - ``rejected`` — reviewed and withheld / removed
    - ``flagged``  — auto-detected risk awaiting review (treated as not
      published until an admin approves it)
    """

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    FLAGGED = "flagged", "Flagged"


# Statuses that mean "not public yet".
NOT_PUBLIC = {ModerationStatus.PENDING, ModerationStatus.REJECTED, ModerationStatus.FLAGGED}


class ReviewModeration(models.Model):
    """One review's moderation assessment (Phase 12.5).

    Companion to :class:`bookings.models.Review` (one per review, created when
    the review is written). A review with *no* moderation record is published
    by default — existing behaviour unchanged. A review whose record is
    ``approved`` is public; ``pending``/``flagged``/``rejected`` are withheld
    from the public review list until an admin decides.

    Only metadata is stored (risk score, detector keys, short signal labels) —
    never the comment text — so the queue never duplicates review content.
    """

    class Meta:
        ordering = ["-created_at"]

    review = models.OneToOneField(
        "bookings.Review",
        on_delete=models.CASCADE,
        related_name="moderation",
    )
    status = models.CharField(
        max_length=10, choices=ModerationStatus.choices, default=ModerationStatus.PENDING
    )
    # 0-100 risk estimate from the deterministic detector suite.
    risk_score = models.PositiveSmallIntegerField(default=0)
    # [{"key", "label", "detail": {...}}, ...] — detector evidence, metadata only.
    signals = models.JSONField(default=list, blank=True)
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review_moderation_decisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"review {self.review_id} → {self.status} ({self.risk_score}/100)"


class PhotoModeration(models.Model):
    """One photo's moderation assessment (Phase 12.5).

    Covers both listing photos (``RoomImage``) and review photos (URLs in a
    review's ``photos`` JSON). Detection reuses the platform's pHash pipeline
    (``rooms.image_search``) to spot re-used / visually duplicated images; the
    risk score and signal list drive the admin queue. Rejected photos are
    withheld from the review list; listing-photo enforcement is a documented
    limitation (the listing serializers are intentionally left untouched).
    """

    class TargetType(models.TextChoices):
        LISTING = "listing", "Listing"
        REVIEW = "review", "Review"

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["target_type", "status"]),
        ]

    target_type = models.CharField(max_length=10, choices=TargetType.choices)
    # The owning entities, depending on target_type. ``room`` is set for
    # listing photos; ``review`` for review photos.
    room = models.ForeignKey(
        "rooms.Room",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="photo_moderations",
    )
    review = models.ForeignKey(
        "bookings.Review",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="photo_moderations",
    )
    # For listing photos: the RoomImage itself (unique per image).
    image = models.ForeignKey(
        "rooms.RoomImage",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderation",
    )
    image_url = models.CharField(max_length=500)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="photo_moderations",
    )
    # Optional perceptual hash (hex) once the image could be read + hashed.
    phash = models.CharField(max_length=16, blank=True)
    status = models.CharField(
        max_length=10, choices=ModerationStatus.choices, default=ModerationStatus.APPROVED
    )
    risk_score = models.PositiveSmallIntegerField(default=0)
    # [{"key", "label", "detail": {...}}, ...] — e.g. duplicate_of, low_quality.
    signals = models.JSONField(default=list, blank=True)
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="photo_moderation_decisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.target_type} photo {self.image_url[:40]} → {self.status} ({self.risk_score}/100)"


__all__ = ["NOT_PUBLIC", "ModerationStatus", "PhotoModeration", "ReviewModeration"]
