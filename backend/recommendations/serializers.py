from rest_framework import serializers

from rooms.serializers import RoomListSerializer


class RecommendationSerializer(serializers.Serializer):
    """A single recommended room plus why it was recommended.

    Not a ModelSerializer — this wraps a computed result (room + score +
    reasons), not a persisted model instance.
    """

    room = RoomListSerializer()
    match_score = serializers.FloatField(help_text="0-100 match confidence.")
    match_reasons = serializers.ListField(child=serializers.CharField())
