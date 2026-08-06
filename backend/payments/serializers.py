from rest_framework import serializers

from bookings.models import Booking

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    """Read representation used for list/retrieve."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "booking",
            "user",
            "amount",
            "payment_method",
            "payment_type",
            "status",
            "transaction_id",
            "gateway_transaction_id",
            "failure_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PaymentInitiateSerializer(serializers.Serializer):
    """Used to start a payment. `amount` is deliberately not accepted here —
    it is always derived server-side from the booking's `monthly_rent`."""

    booking_id = serializers.PrimaryKeyRelatedField(
        queryset=Booking.objects.all(), source="booking"
    )
    payment_type = serializers.ChoiceField(choices=Payment.Type.choices)

    def validate(self, attrs):
        request = self.context["request"]
        booking = attrs["booking"]

        if booking.tenant_id != request.user.id:
            raise serializers.ValidationError("You can only pay for your own bookings.")

        if booking.status != Booking.Status.APPROVED:
            raise serializers.ValidationError("Only approved bookings can be paid for.")

        return attrs
