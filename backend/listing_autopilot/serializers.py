"""Listing Autopilot request serializers (Phase 19.3)."""

from rest_framework import serializers


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        value["reason"] = (value.get("reason") or "").strip()
        return value


class BulkApproveSerializer(serializers.Serializer):
    proposal_keys = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=True, max_length=200
    )
