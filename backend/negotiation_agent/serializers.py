"""AI Negotiation Agent — API serializers (Phase 19.4)."""

from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    conversation_id = serializers.IntegerField(required=False, allow_null=True)
    message = serializers.CharField(max_length=4000, allow_blank=False)
    room_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_message(self, value):
        return value.strip()


class ConsentRequestSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_note(self, value):
        return (value or "").strip()
