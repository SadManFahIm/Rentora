"""Rentora AI Rental Agent — API serializers (Phase 19.2)."""

from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    conversation_id = serializers.IntegerField(required=False, allow_null=True)
    message = serializers.CharField(max_length=4000, allow_blank=False)

    def validate_message(self, value):
        return value.strip()


class ConsentRequestSerializer(serializers.Serializer):
    """Tenant self-consent for a pending bookmark proposal."""

    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_note(self, value):
        return (value or "").strip()
