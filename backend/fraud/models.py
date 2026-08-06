"""Fraud-detection domain models.

A ``FraudReport`` is one room's overall risk assessment (one per room), and
the individual ``FraudSignal`` rows record *why* it got the score it did —
each detector contributes one signal with its own severity and a machine
readable detail blob. Keeping signals as separate rows means a landlord can
see "duplicate listing + suspicious price" rather than one opaque number.
"""

from django.conf import settings
from django.db import models

from rooms.models import Room


class FraudReport(models.Model):
    """Aggregate fraud-risk assessment for a single room."""

    class Severity(models.TextChoices):
        CLEAN = "clean", "Clean"
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWED = "reviewed", "Reviewed"
        DISMISSED = "dismissed", "Dismissed"

    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name="fraud_report")
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.CLEAN
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    score = models.IntegerField(default=0, help_text="0-100 aggregate risk score.")
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score"]

    def __str__(self):
        return f"{self.room.title} [{self.severity}] {self.score}"

    @property
    def is_flagged(self) -> bool:
        return self.severity in (FraudReport.Severity.LOW, FraudReport.Severity.MEDIUM, FraudReport.Severity.HIGH)


class FraudSignal(models.Model):
    """One detector's finding for a room, with evidence."""

    class Detector(models.TextChoices):
        DUPLICATE_LISTING = "duplicate_listing", "Duplicate Listing"
        SUSPICIOUS_PRICE = "suspicious_price", "Suspicious Price"
        MISSING_IMAGES = "missing_images", "Missing Images"
        RAPID_LISTING = "rapid_listing", "Rapid Listing"
        UNVERIFIED_OWNER = "unverified_owner", "Unverified Owner"
        DESCRIPTION_SIMILARITY = "description_similarity", "Description Similarity"

    report = models.ForeignKey(FraudReport, on_delete=models.CASCADE, related_name="signals")
    detector = models.CharField(max_length=30, choices=Detector.choices)
    severity = models.CharField(max_length=10, choices=FraudReport.Severity.choices)
    message = models.TextField()
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-severity", "detector"]

    def __str__(self):
        return f"{self.get_detector_display()} [{self.severity}]"
