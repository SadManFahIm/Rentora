from rest_framework import serializers

from rooms.models import Room

from .models import InsuranceProduct, InsuranceQuote


class InsuranceProductSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source="partner.name", read_only=True)

    class Meta:
        model = InsuranceProduct
        fields = [
            "id",
            "partner",
            "partner_name",
            "code",
            "name",
            "coverage",
            "price_monthly",
            "deductible",
            "is_active",
        ]
        read_only_fields = fields


class InsuranceQuoteSerializer(serializers.ModelSerializer):
    product = InsuranceProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=InsuranceProduct.objects.filter(is_active=True), source="product", write_only=True
    )
    room_id = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        source="room",
        write_only=True,
        required=False,
        allow_null=True,
    )
    broker_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = InsuranceQuote
        fields = [
            "id",
            "product",
            "product_id",
            "room_id",
            "broker_code",
            "price",
            "coverage_period",
            "status",
            "status_display",
            "quote_data",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "product",
            "price",
            "coverage_period",
            "status",
            "status_display",
            "quote_data",
            "created_at",
        ]

    def validate_broker_code(self, value):
        if not value:
            return None
        from brokers.services import resolve_referral

        broker = resolve_referral(value)
        if broker is None:
            raise serializers.ValidationError("Invalid or unverified broker code.")
        return broker

    def create(self, validated_data):
        from .services import create_quote

        broker = validated_data.pop("broker_code", None)
        validated_data["broker"] = broker
        user = self.context["request"].user
        return create_quote(user=user, **validated_data)
