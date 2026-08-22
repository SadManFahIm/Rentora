"""Fraud-detection domain models.

A ``FraudReport`` is one room's overall risk assessment (one per room), and
the individual ``FraudSignal`` rows record *why* it got the score it did —
each detector contributes one signal with its own severity and a machine
readable detail blob. Keeping signals as separate rows means a landlord can
see "duplicate listing + suspicious price" rather than one opaque number.

Stage 3 adds a persistent fraud graph (``GraphNode`` / ``GraphEdge``) used
for scam-network detection and community analysis.  The graph is rebuilt
weekly and incrementally updated every 6 hours.
"""

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
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.CLEAN)
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
        return self.severity in (
            FraudReport.Severity.LOW,
            FraudReport.Severity.MEDIUM,
            FraudReport.Severity.HIGH,
        )


class FraudSignal(models.Model):
    """One detector's finding for a room, with evidence."""

    class Detector(models.TextChoices):
        DUPLICATE_LISTING = "duplicate_listing", "Duplicate Listing"
        SUSPICIOUS_PRICE = "suspicious_price", "Suspicious Price"
        MISSING_IMAGES = "missing_images", "Missing Images"
        RAPID_LISTING = "rapid_listing", "Rapid Listing"
        UNVERIFIED_OWNER = "unverified_owner", "Unverified Owner"
        DESCRIPTION_SIMILARITY = "description_similarity", "Description Similarity"
        DUPLICATE_IMAGE = "duplicate_image", "Duplicate Image"
        MANIPULATED_IMAGE = "manipulated_image", "Manipulated Image"
        FRAUD_RING = "fraud_ring", "Fraud Ring"
        # Phase 17 — Graph & Deep Trust (detector implementations in Stages 3-7)
        PHOTO_GEO_MISMATCH = "photo_geo_mismatch", "Photo-Geo Mismatch"
        LIVENESS_FAILED = "liveness_failed", "Liveness Check Failed"
        FACE_MATCH_FAILED = "face_match_failed", "Face Match Failed"
        REVIEW_FAKE = "review_fake", "Fake Review Detected"
        REVIEW_SPAM = "review_spam", "Review Spam Detected"
        KYC_LIVENESS_MISSING = "kyc_liveness_missing", "KYC Liveness Not Completed"

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


# ---------------------------------------------------------------------------
# Stage 3 — Persistent Fraud Graph (Scam-Network Detection)
# ---------------------------------------------------------------------------


class GraphNode(models.Model):
    """One entity in the persistent fraud graph.

    Entity types: ``user`` (account), ``room`` (listing), ``device`` (browser
    or device fingerprint), ``payment`` (bank account / mobile money number).

    Nodes are keyed by (entity_type, entity_id) and carry a computed
    ``risk_score`` updated by the graph rebuild task.
    """

    class EntityType(models.TextChoices):
        USER = "user", "User"
        ROOM = "room", "Room"
        DEVICE = "device", "Device"
        PAYMENT = "payment", "Payment"

    entity_type = models.CharField(max_length=16, choices=EntityType.choices)
    entity_id = models.CharField(max_length=100)
    label = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable label (username, room title, etc.).",
    )
    metadata = models.JSONField(default=dict, blank=True)
    risk_score = models.IntegerField(
        default=0,
        help_text="0-100 risk score computed from connected edges and neighbours.",
    )
    community_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Community cluster id assigned by the last graph rebuild.",
    )
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-risk_score", "-last_seen"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["entity_type", "risk_score"]),
            models.Index(fields=["community_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["entity_type", "entity_id"],
                name="uq_graph_node_entity",
            ),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} [{self.risk_score}]"


class GraphEdge(models.Model):
    """One edge in the persistent fraud graph.

    Edges link two ``GraphNode`` instances.  Each edge has a type (phone
    share, IP share, device fingerprint, NID reuse, payment path,
    behavioural similarity), a strength category, and a weighted score used
    for community detection and risk propagation.
    """

    class EdgeType(models.TextChoices):
        PHONE = "phone", "Shared Phone"
        IP = "ip", "Shared IP"
        DEVICE = "device", "Shared Device"
        NID = "nid", "Shared NID"
        PAYMENT = "payment", "Shared Payment"
        BEHAVIORAL = "behavioral", "Behavioral Similarity"

    class Strength(models.TextChoices):
        STRONG = "strong", "Strong"
        WEAK = "weak", "Weak"
        POTENTIAL = "potential", "Potential"

    source = models.ForeignKey(GraphNode, on_delete=models.CASCADE, related_name="outgoing_edges")
    target = models.ForeignKey(GraphNode, on_delete=models.CASCADE, related_name="incoming_edges")
    edge_type = models.CharField(max_length=16, choices=EdgeType.choices)
    strength = models.CharField(max_length=10, choices=Strength.choices, default=Strength.WEAK)
    weight = models.FloatField(
        default=0.5,
        help_text="0.0-1.0 weight used for community detection and risk propagation.",
    )
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="Supporting data: phone number, IP address, device id, etc.",
    )
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-weight"]
        indexes = [
            models.Index(fields=["edge_type", "last_seen"]),
            models.Index(fields=["source", "target"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target", "edge_type"],
                name="uq_graph_edge_pair_type",
            ),
        ]

    def __str__(self):
        return f"{self.source} --[{self.edge_type}]--> {self.target} (w={self.weight})"
