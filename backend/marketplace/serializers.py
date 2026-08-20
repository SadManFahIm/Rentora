from rest_framework import serializers

from .models import AddonOrder, AddonProvider, AddonService


class AddonProviderSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    is_active = serializers.BooleanField(source="is_active", read_only=True)

    class Meta:
        model = AddonProvider
        fields = [
            "id",
            "user",
            "user_name",
            "business_name",
            "description",
            "status",
            "commission_rate",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "user", "user_name", "status", "is_active", "created_at"]


class AddonServiceSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.business_name", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = AddonService
        fields = [
            "id",
            "provider",
            "provider_name",
            "category",
            "category_display",
            "title",
            "description",
            "price",
            "unit",
            "is_active",
            "rating_avg",
            "rating_count",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "provider",
            "provider_name",
            "rating_avg",
            "rating_count",
            "created_at",
        ]


class AddonOrderSerializer(serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True)
    provider_business = serializers.CharField(
        source="service.provider.business_name", read_only=True
    )
    tenant_name = serializers.CharField(source="tenant.username", read_only=True)
    broker_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = AddonOrder
        fields = [
            "id",
            "service",
            "service_title",
            "provider_business",
            "tenant",
            "tenant_name",
            "broker_code",
            "quantity",
            "total",
            "status",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "tenant", "tenant_name", "total", "status", "created_at"]

    def validate_broker_code(self, value):
        if not value:
            return None
        from brokers.services import resolve_referral

        broker = resolve_referral(value)
        if broker is None:
            raise serializers.ValidationError("Invalid or unverified broker code.")
        return broker

    def validate(self, attrs):
        service = attrs["service"]
        if not service.is_active or not service.provider.is_active():
            raise serializers.ValidationError("This service is not available.")
        return attrs

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].user
        broker = validated_data.pop("broker_code", None)
        validated_data["broker"] = broker
        order = super().create(validated_data)
        order.total = order.service.price * order.quantity
        order.save(update_fields=["total"])
        return order
