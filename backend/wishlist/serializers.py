from rest_framework import serializers

from rooms.models import Room
from rooms.serializers import RoomListSerializer

from .models import Wishlist


class WishlistSerializer(serializers.ModelSerializer):
    """Serialize a wishlist entry.

    On read it embeds the full room summary (``RoomListSerializer``); on write
    it accepts only ``room_id``, resolved against available rooms. ``user`` is
    always taken from the request in the view, never from the payload.
    """

    room = RoomListSerializer(read_only=True)
    room_id = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        source="room",
        write_only=True,
    )

    class Meta:
        model = Wishlist
        fields = ["id", "room", "room_id", "created_at"]
        read_only_fields = ["id", "created_at"]
