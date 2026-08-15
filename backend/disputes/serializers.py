from rest_framework import serializers

from .models import Dispute, DisputeEvidence


class DisputeEvidenceSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = DisputeEvidence
        fields = [
            "id",
            "dispute",
            "uploaded_by",
            "uploaded_by_username",
            "kind",
            "kind_display",
            "content",
            "file",
            "created_at",
        ]
        read_only_fields = ["dispute", "uploaded_by", "created_at"]


class DisputeSerializer(serializers.ModelSerializer):
    """List/read representation of a dispute for its participants or admins."""

    opened_by_username = serializers.CharField(source="opened_by.username", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    decision_display = serializers.CharField(source="get_decision_display", read_only=True)
    room_title = serializers.CharField(source="booking.room.title", read_only=True)
    room_id = serializers.IntegerField(source="booking.room_id", read_only=True)
    other_party_username = serializers.SerializerMethodField()
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id",
            "booking",
            "room_id",
            "room_title",
            "opened_by",
            "opened_by_username",
            "other_party_username",
            "category",
            "category_display",
            "description",
            "status",
            "status_display",
            "decision",
            "decision_display",
            "decision_amount",
            "resolution",
            "evidence",
            "created_at",
            "updated_at",
            "resolved_at",
        ]
        read_only_fields = fields

    def get_other_party_username(self, obj: Dispute) -> str:
        booking = obj.booking
        if obj.opened_by_id == booking.tenant_id:
            return booking.room.owner.username
        return booking.tenant.username


class DisputeCreateSerializer(serializers.Serializer):
    booking = serializers.IntegerField()
    category = serializers.ChoiceField(choices=Dispute.Category.choices)
    description = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=4000
    )


class DisputeActionSerializer(serializers.Serializer):
    """Admin decision on a dispute: transition | resolve | reject.

    ``action`` decides what the payload means:

    - ``transition``: move status (under_review / waiting_for_tenant /
      waiting_for_landlord / escalated) — `status` required.
    - ``resolve``: close as resolved with a `decision` (and optional
      `decision_amount` + `resolution` text). Deposit decisions mark the
      booking's deposit as released/refunded.
    - ``reject``: close without a decision — `resolution` recommended.
    """

    action = serializers.ChoiceField(choices=["transition", "resolve", "reject"])
    status = serializers.ChoiceField(
        choices=[
            Dispute.Status.UNDER_REVIEW,
            Dispute.Status.WAITING_FOR_TENANT,
            Dispute.Status.WAITING_FOR_LANDLORD,
            Dispute.Status.ESCALATED,
        ],
        required=False,
    )
    decision = serializers.ChoiceField(
        choices=[
            Dispute.Decision.NONE,
            Dispute.Decision.RELEASE_TO_LANDLORD,
            Dispute.Decision.REFUND_TO_TENANT,
            Dispute.Decision.PARTIAL_RESOLUTION,
        ],
        required=False,
    )
    decision_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    resolution = serializers.CharField(required=False, allow_blank=True, default="")
