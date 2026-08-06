"""Roommate matching domain models.

Two models:

- ``RoommateProfile`` — what a user is looking for (and offering): budget
  range, preferred area, room-type preference, gender preference, lifestyle
  tags and a short bio. One profile per user.
- ``RoommateMatchRequest`` — a user asks another user to share a room.
  Sender/receiver are directional; the receiver approves or rejects.
"""

from django.conf import settings
from django.db import models

from rooms.models import Room


class RoommateProfile(models.Model):
    """A user's roommate-seeking profile.

    ``lifestyle`` holds free-form tags chosen from the platform vocabulary
    (e.g. ``early_bird``, ``non_smoker``, ``student``) so the matcher can
    score compatibility with a Jaccard-style overlap; the tags are validated
    against ``LIFESTYLE_TAGS`` at the serializer layer.
    """

    LIFESTYLE_TAGS = [
        "early_bird",
        "night_owl",
        "non_smoker",
        "smoker",
        "student",
        "working_professional",
        "quiet",
        "social",
        "veggie",
        "pet_friendly",
        "clean",
        "guest_friendly",
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roommate_profile",
    )

    budget_min = models.DecimalField(max_digits=10, decimal_places=2)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2)
    preferred_area = models.CharField(max_length=50, choices=Room.Area.choices)
    room_type_pref = models.CharField(max_length=10, choices=Room.RoomType.choices)
    gender_pref = models.CharField(
        max_length=10, choices=Room.GenderPreference.choices, default=Room.GenderPreference.ANY
    )
    lifestyle = models.JSONField(default=list, blank=True)
    occupation = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    move_in_date = models.DateField(null=True, blank=True)
    is_looking = models.BooleanField(default=True, help_text="Currently open to matches.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user} roommate profile ({self.preferred_area})"


class RoommateMatchRequest(models.Model):
    """A roommate-sharing request from ``sender`` to ``receiver``."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_roommate_requests"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_roommate_requests"
    )
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "receiver"],
                name="unique_roommate_request_pair",
            )
        ]

    def __str__(self):
        return f"{self.sender} -> {self.receiver} ({self.status})"
