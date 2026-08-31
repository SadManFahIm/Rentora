"""AI Listing Autopilot models — Phase 19.3.

The autopilot does NOT introduce a second proposal store: every recommendation
the landlord reviews and every state-changing action the agent executes is a
Phase 19.0 ``AgentProposal`` (its lifecycle lives in the Agent SDK). This app
adds only lightweight, time-boxed coordination state:

* ``ListingAnalysis`` — a per-(room, week) immutable snapshot of the
  deterministic analysis: the inputs the recommendation was grounded on
  (score, price payload, quality, photo gaps, eligibility) and a stable
  ``grounding_key`` (a hash of the room state the proposals were built
  against). It powers idempotency (one analysis per room per week) and the
  landlord dashboard score, without recomputing or duplicating the Phase 19.1 /
  Phase 15 engines.

All proposal content (title, description, amenities, price, photos, renewal) is
carried in ``AgentProposal`` rows keyed by their ``proposal_type``. Nothing in
this app is editable free-form state — it is derived, audited, and regenerated
weekly.
"""

from django.db import models


class ProposalType(models.TextChoices):
    """The typed, landlord-reviewable recommendation the autopilot can emit."""

    TITLE_UPDATE = "TITLE_UPDATE", "Title update"
    DESCRIPTION_UPDATE = "DESCRIPTION_UPDATE", "Description update"
    AMENITY_UPDATE = "AMENITY_UPDATE", "Amenities update"
    PHOTO_RECOMMENDATION = "PHOTO_RECOMMENDATION", "Photo recommendation"
    PRICE_UPDATE = "PRICE_UPDATE", "Price update"
    LISTING_RENEWAL = "LISTING_RENEWAL", "Listing renewal"


class ListingAnalysis(models.Model):
    """A weekly analysis snapshot for one listing.

    ``UniqueConstraint(room, week_key)`` guarantees at most one analysis per
    listing per weekly run — the Celery task is idempotent by construction.
    The full deterministic payload is stored so the dashboard renders the
    score/grounding without recomputing; nothing here invents values.
    """

    room = models.ForeignKey(
        "rooms.Room", on_delete=models.CASCADE, related_name="autopilot_analyses"
    )
    week_key = models.CharField(max_length=16, db_index=True)
    eligible = models.BooleanField(default=False)
    eligibility_blocks = models.JSONField(default=list, blank=True)

    # Grounding snapshot derived from the (reused) deterministic engines.
    quality_score = models.IntegerField(null=True, blank=True)
    quality_level = models.CharField(max_length=16, blank=True, default="")
    property_score = models.IntegerField(null=True, blank=True)
    property_confidence = models.CharField(max_length=16, blank=True, default="")
    price_direction = models.CharField(max_length=8, blank=True, default="hold")
    suggested_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    photo_count = models.IntegerField(default=0)
    stale_days = models.IntegerField(default=0)

    # Hash of the room state the proposals were grounded against. Any room
    # change mints a new hash, so a stale proposal is detected server-side.
    grounding_key = models.CharField(max_length=64, db_index=True, blank=True, default="")

    payload = models.JSONField(default=dict, blank=True)
    summary = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Listing analysis"
        verbose_name_plural = "Listing analyses"
        constraints = [
            models.UniqueConstraint(
                fields=["room", "week_key"],
                name="uniq_autopilot_analysis_room_week",
            )
        ]

    def __str__(self):
        return f"analysis {self.room_id} / {self.week_key} ({'eligible' if self.eligible else 'skipped'})"
