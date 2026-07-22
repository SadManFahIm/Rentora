from datetime import date

from rest_framework import serializers

from config.sanitizers import sanitize_text
from rooms.models import Room
from rooms.serializers import RoomOwnerSerializer

from .models import Booking, Review


class BookingRoomSerializer(serializers.ModelSerializer):
    """Lightweight room representation embedded in booking responses."""

    class Meta:
        model = Room
        fields = ["id", "title", "area", "price"]


class BookingSerializer(serializers.ModelSerializer):
    """Read representation used for list/retrieve."""

    room = BookingRoomSerializer(read_only=True)
    tenant = RoomOwnerSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "room",
            "tenant",
            "status",
            "check_in",
            "check_out",
            "monthly_rent",
            "agreement_signed",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class BookingCreateSerializer(serializers.ModelSerializer):
    """Used by tenants to create a booking. `tenant` is set from the request in the view."""

    class Meta:
        model = Booking
        fields = ["id", "room", "check_in", "check_out", "monthly_rent", "notes"]
        extra_kwargs = {"monthly_rent": {"required": False}}

    def validate(self, attrs):
        request = self.context["request"]
        room = attrs["room"]

        if room.owner_id == request.user.id:
            raise serializers.ValidationError("You cannot book your own room.")

        if not room.is_available:
            raise serializers.ValidationError("This room is not available for booking.")

        check_in = attrs["check_in"]
        check_out = attrs.get("check_out")
        blocking_statuses = [Booking.Status.PENDING, Booking.Status.APPROVED]
        for existing in Booking.objects.filter(room=room, status__in=blocking_statuses):
            existing_end = existing.check_out or date.max
            new_end = check_out or date.max
            if existing.check_in <= new_end and existing_end >= check_in:
                raise serializers.ValidationError(
                    "This room already has an overlapping booking for those dates."
                )

        return attrs

    def create(self, validated_data):
        validated_data.setdefault("monthly_rent", validated_data["room"].price)
        validated_data["tenant"] = self.context["request"].user
        return super().create(validated_data)


class BookingUpdateSerializer(serializers.ModelSerializer):
    """Used for PATCH: the landlord approves/rejects, the tenant cancels; either
    party may mark the agreement signed once the booking is approved."""

    class Meta:
        model = Booking
        fields = ["status", "agreement_signed", "notes"]

    def validate(self, attrs):
        request = self.context["request"]
        booking = self.instance
        user = request.user
        is_owner = booking.room.owner_id == user.id
        is_tenant = booking.tenant_id == user.id

        new_status = attrs.get("status")
        if new_status and new_status != booking.status:
            if is_owner and not is_tenant:
                allowed = {
                    Booking.Status.PENDING: {Booking.Status.APPROVED, Booking.Status.REJECTED},
                }
            elif is_tenant:
                allowed = {
                    Booking.Status.PENDING: {Booking.Status.CANCELLED},
                    Booking.Status.APPROVED: {Booking.Status.CANCELLED},
                }
            else:
                raise serializers.ValidationError("You do not have permission to change this booking's status.")

            valid_targets = allowed.get(booking.status, set())
            if new_status not in valid_targets:
                raise serializers.ValidationError(
                    f"Cannot transition booking from '{booking.status}' to '{new_status}'."
                )

        if attrs.get("agreement_signed") and booking.status != Booking.Status.APPROVED:
            raise serializers.ValidationError("The agreement can only be signed once the booking is approved.")

        return attrs


class ReviewSerializer(serializers.ModelSerializer):
    """Read representation used for list/retrieve."""

    user = RoomOwnerSerializer(read_only=True)

    class Meta:
        model = Review
        fields = ["id", "room", "user", "rating", "comment", "verified_stay", "created_at"]
        read_only_fields = fields


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "room", "rating", "comment"]

    def validate_comment(self, value: str) -> str:
        """Strip any HTML from the review comment to prevent stored XSS."""
        return sanitize_text(value)

    def validate(self, attrs):
        request = self.context["request"]
        room = attrs["room"]

        if Review.objects.filter(room=room, user=request.user).exists():
            raise serializers.ValidationError("You have already reviewed this room.")

        has_approved_booking = Booking.objects.filter(
            room=room, tenant=request.user, status=Booking.Status.APPROVED
        ).exists()
        if not has_approved_booking:
            raise serializers.ValidationError("You can only review rooms you have an approved booking for.")

        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        validated_data["verified_stay"] = True  # validate() already required an approved booking
        return super().create(validated_data)
