"""Serializers for the roommates app."""

from rest_framework import serializers

from config.sanitizers import sanitize_text
from rooms.serializers import RoomOwnerSerializer

from .models import RoommateMatchRequest, RoommateProfile


class RoommateProfileSerializer(serializers.ModelSerializer):
    """Write/read serializer for the current user's own profile."""

    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = RoommateProfile
        fields = [
            "id",
            "username",
            "budget_min",
            "budget_max",
            "preferred_area",
            "room_type_pref",
            "gender_pref",
            "lifestyle",
            "occupation",
            "bio",
            "move_in_date",
            "is_looking",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_lifestyle(self, value):
        allowed = set(RoommateProfile.LIFESTYLE_TAGS)
        unknown = [tag for tag in (value or []) if tag not in allowed]
        if unknown:
            raise serializers.ValidationError(
                {"lifestyle": f"Unknown lifestyle tags: {', '.join(unknown)}"}
            )
        return value

    def validate(self, attrs):
        budget_min = attrs.get("budget_min")
        budget_max = attrs.get("budget_max")
        if budget_min is not None and budget_max is not None and budget_min > budget_max:
            raise serializers.ValidationError(
                {"budget_min": "Minimum budget cannot exceed maximum budget."}
            )
        return attrs

    def validate_occupation(self, value):
        return sanitize_text(value) or ""

    def validate_bio(self, value):
        return sanitize_text(value) or ""


class RoommateProfilePublicSerializer(RoommateProfileSerializer):
    """What other users see when browsing matches — no email, no exact
    location; the owner object is the same public-safe subset used in rooms."""

    user = serializers.SerializerMethodField()

    class Meta(RoommateProfileSerializer.Meta):
        fields = [*RoommateProfileSerializer.Meta.fields, "user"]
        read_only_fields = [*RoommateProfileSerializer.Meta.read_only_fields, "user"]

    def get_user(self, obj):
        return RoomOwnerSerializer(obj.user, context=self.context).data


class RoommateMatchSerializer(serializers.Serializer):
    """A scored match: the public profile plus why it matched."""

    score = serializers.IntegerField()
    reasons = serializers.ListField(child=serializers.CharField())
    profile = RoommateProfilePublicSerializer()


class RoommateRequestSerializer(serializers.ModelSerializer):
    """Request lifecycle — read everything, write only message + receiver."""

    sender = RoomOwnerSerializer(read_only=True)
    receiver = RoomOwnerSerializer(read_only=True)
    receiver_id = serializers.IntegerField(write_only=True)
    direction = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RoommateMatchRequest
        fields = [
            "id",
            "sender",
            "receiver",
            "receiver_id",
            "message",
            "status",
            "status_display",
            "direction",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "sender", "receiver", "status", "created_at", "updated_at"]

    def get_direction(self, obj):
        request = self.context.get("request")
        if request and obj.sender_id == request.user.id:
            return "outgoing"
        if request and obj.receiver_id == request.user.id:
            return "incoming"
        return ""

    def validate_message(self, value):
        return sanitize_text(value) or ""


class RoommateRequestActionSerializer(serializers.Serializer):
    """Payload for approving/rejecting an incoming request."""

    action = serializers.ChoiceField(choices=["approve", "reject"])


class RoommateRequestCreateSerializer(serializers.ModelSerializer):
    """Strictly write-oriented — used for POST /roommates/requests/."""

    receiver_id = serializers.IntegerField()

    class Meta:
        model = RoommateMatchRequest
        fields = ["receiver_id", "message"]

    def validate_message(self, value):
        return sanitize_text(value) or ""
