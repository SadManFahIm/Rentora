"""Serializers for the fraud app."""

from rest_framework import serializers

from rooms.serializers import RoomListSerializer

from .models import FraudReport, FraudSignal


class FraudSignalSerializer(serializers.ModelSerializer):
    detector_display = serializers.CharField(source="get_detector_display", read_only=True)

    class Meta:
        model = FraudSignal
        fields = [
            "id",
            "detector",
            "detector_display",
            "severity",
            "message",
            "detail",
            "created_at",
        ]
        read_only_fields = fields


class FraudReportSerializer(serializers.ModelSerializer):
    """Report with signals, plus a room summary so list views don't need a
    second fetch for the card image/title."""

    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    signals = FraudSignalSerializer(many=True, read_only=True)
    room = RoomListSerializer(read_only=True)

    class Meta:
        model = FraudReport
        fields = [
            "id",
            "room",
            "severity",
            "severity_display",
            "status",
            "status_display",
            "score",
            "summary",
            "signals",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "room",
            "severity",
            "status",
            "score",
            "summary",
            "signals",
            "created_at",
            "updated_at",
        ]


class FraudStatusSerializer(serializers.Serializer):
    """Public, per-room fraud status — enough for a badge, nothing sensitive."""

    room_id = serializers.IntegerField()
    severity = serializers.ChoiceField(choices=FraudReport.Severity.choices)
    score = serializers.IntegerField()
    flagged = serializers.BooleanField()
    message = serializers.CharField()


class FraudReviewRequestSerializer(serializers.Serializer):
    """Admin decision on an open report."""

    action = serializers.ChoiceField(choices=["reviewed", "dismissed"])


class GraphNodeSerializer(serializers.ModelSerializer):
    entity_type_display = serializers.CharField(source="get_entity_type_display", read_only=True)

    class Meta:
        from .models import GraphNode

        model = GraphNode
        fields = [
            "id",
            "entity_type",
            "entity_type_display",
            "entity_id",
            "label",
            "metadata",
            "risk_score",
            "community_id",
            "first_seen",
            "last_seen",
        ]
        read_only_fields = fields


class GraphEdgeSerializer(serializers.ModelSerializer):
    edge_type_display = serializers.CharField(source="get_edge_type_display", read_only=True)
    strength_display = serializers.CharField(source="get_strength_display", read_only=True)

    class Meta:
        from .models import GraphEdge

        model = GraphEdge
        fields = [
            "id",
            "source",
            "target",
            "edge_type",
            "edge_type_display",
            "strength",
            "strength_display",
            "weight",
            "evidence",
            "first_seen",
            "last_seen",
        ]
        read_only_fields = fields
