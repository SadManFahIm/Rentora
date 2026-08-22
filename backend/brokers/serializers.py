from rest_framework import serializers

from .models import BrokerProfile, BrokerVerification


class BrokerProfileSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    is_verified = serializers.BooleanField(source="is_verified", read_only=True)

    class Meta:
        model = BrokerProfile
        fields = [
            "id",
            "user",
            "user_name",
            "license_number",
            "years_experience",
            "specialization",
            "areas",
            "referral_code",
            "status",
            "is_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "user_name",
            "referral_code",
            "status",
            "is_verified",
            "created_at",
            "updated_at",
        ]


class BrokerVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrokerVerification
        fields = [
            "id",
            "profile",
            "documents",
            "notes",
            "status",
            "auto_screen_score",
            "auto_screen_result",
            "auto_screen_detail",
            "created_at",
            "reviewed_at",
        ]
        read_only_fields = fields
