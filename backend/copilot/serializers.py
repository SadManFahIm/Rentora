from rest_framework import serializers


class CopilotChatRequestSerializer(serializers.Serializer):
    """One Copilot turn. ``session_id`` is optional — omit it to start a new
    conversation (the response returns one to echo back for follow-ups)."""

    message = serializers.CharField(
        min_length=1, max_length=500, help_text="Free-text request, Bangla or English."
    )
    session_id = serializers.CharField(required=False, allow_blank=True, default="")


class CopilotIntentSerializer(serializers.Serializer):
    budget_max = serializers.IntegerField(allow_null=True)
    areas = serializers.ListField(child=serializers.CharField())
    room_type = serializers.CharField(allow_null=True)
    gender = serializers.CharField(allow_null=True)
    months = serializers.ListField(child=serializers.CharField())
    amenities = serializers.ListField(child=serializers.CharField())
    property_words = serializers.ListField(child=serializers.CharField())
    hints = serializers.ListField(child=serializers.CharField())


class CopilotListingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    price = serializers.FloatField()
    area = serializers.CharField()
    room_type = serializers.CharField()
    amenities = serializers.ListField(child=serializers.CharField())
    verified = serializers.BooleanField()
    tier = serializers.CharField()
    image = serializers.CharField(allow_null=True)


class CopilotChatResponseSerializer(serializers.Serializer):
    """Structured Copilot reply: a human message plus the *retrieved* rooms
    and the interpreted intent (chips) so the UI never parses prose."""

    session_id = serializers.CharField()
    message = serializers.CharField()
    intent = CopilotIntentSerializer()
    listings = CopilotListingSerializer(many=True)
    total_count = serializers.IntegerField()
    suggestions = serializers.ListField(child=serializers.CharField())
