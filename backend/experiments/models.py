"""Experimentation / A/B testing foundation (Phase 16).

* deterministic assignment — the same eligible user stays in the same variant
  (bucketed by ``user.id`` / ``anonymous_id``, never re-randomised per request);
* explicit exposure tracking — counted when a user actually *sees* a variant,
  not on every API call;
* conversion tracking — bookings/subscriptions/payments can be attributed to
  the assigned variant via ``record_conversion``.

Eligibility is only the *assignment* gate. A user outside the experiment's
traffic allocation is "not assigned" and never sees a variant.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class Experiment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    key = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    owner = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    traffic_allocation = models.PositiveIntegerField(default=100)  # 0..100
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key

    @property
    def is_running(self) -> bool:
        now = timezone.now()
        return (
            self.status == self.Status.ACTIVE
            and (self.start_at is None or self.start_at <= now)
            and (self.end_at is None or self.end_at >= now)
        )


class ExperimentVariant(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name="variants")
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=200, blank=True, default="")
    weight = models.PositiveIntegerField(default=1)  # relative weight
    is_control = models.BooleanField(default=False)

    class Meta:
        ordering = ["experiment_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["experiment", "key"], name="variant_experiment_key_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.experiment.key}:{self.key}"


class ExperimentAssignment(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name="assignments")
    variant = models.ForeignKey(
        ExperimentVariant, on_delete=models.CASCADE, related_name="assignments"
    )
    assignee_key = models.CharField(max_length=128, db_index=True)  # user:{id} | anon:{id} | ip:...
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="experiment_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["experiment", "assignee_key"], name="assignment_experiment_key_unique"
            )
        ]


class ExperimentExposure(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name="exposures")
    variant = models.ForeignKey(
        ExperimentVariant, on_delete=models.CASCADE, related_name="exposures"
    )
    assignee_key = models.CharField(max_length=128, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="experiment_exposures",
    )
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["experiment", "assignee_key"], name="exposure_experiment_user_idx"
            ),
        ]
