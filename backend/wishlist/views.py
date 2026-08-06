from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rooms.models import Room

from .models import Wishlist
from .serializers import WishlistSerializer


@extend_schema_view(
    list=extend_schema(
        tags=["Wishlist"],
        summary="List saved rooms",
        description="The authenticated user's wishlisted rooms (newest first).",
    ),
    destroy=extend_schema(
        tags=["Wishlist"],
        summary="Remove a wishlist entry",
        description="Delete a specific wishlist entry by its id.",
    ),
)
class WishlistViewSet(
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Manage the authenticated user's saved rooms.

    Endpoints
    ---------
    * ``GET  /api/v1/wishlist/``        — list the user's wishlisted rooms.
    * ``POST /api/v1/wishlist/toggle/`` — add/remove a room by ``room_id``.
    * ``DELETE /api/v1/wishlist/{id}/`` — remove a specific wishlist entry.
    """

    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Only ever expose the requesting user's own entries.

        ``room`` and its images/owner are pulled in the same query set to keep
        the nested ``RoomListSerializer`` free of N+1 lookups.
        """
        if getattr(self, "swagger_fake_view", False):
            return Wishlist.objects.none()
        return (
            Wishlist.objects.filter(user=self.request.user)
            .select_related("room", "room__owner")
            .prefetch_related("room__images")
        )

    @extend_schema(
        tags=["Wishlist"],
        summary="Toggle a room in the wishlist",
        description=(
            "Add the room if it is not already saved, remove it if it is. "
            "Idempotent per call — the response reports the resulting state."
        ),
        request=inline_serializer(
            "WishlistToggleRequest",
            fields={"room_id": serializers.IntegerField()},
        ),
        responses=inline_serializer(
            "WishlistToggleResponse",
            fields={
                # Plain CharField (not a ChoiceField) so this ad-hoc "status"
                # doesn't register as an enum and collide with Booking.status.
                "status": serializers.CharField(),
                "wishlisted": serializers.BooleanField(),
            },
        ),
        examples=[
            OpenApiExample("Toggle", value={"room_id": 1}, request_only=True),
            OpenApiExample("Added", value={"status": "added", "wishlisted": True}, response_only=True),
            OpenApiExample("Removed", value={"status": "removed", "wishlisted": False}, response_only=True),
        ],
    )
    @action(detail=False, methods=["post"])
    def toggle(self, request: Request) -> Response:
        """Add the room to the wishlist if absent, remove it if present.

        Body: ``{"room_id": <int>}``. Responds with the resulting state so the
        client can update its UI without a follow-up request::

            {"status": "added"|"removed", "wishlisted": true|false}
        """
        room_id = request.data.get("room_id")
        if room_id is None:
            return Response(
                {"detail": "room_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        room = get_object_or_404(Room, pk=room_id)

        entry = Wishlist.objects.filter(user=request.user, room=room).first()
        if entry is not None:
            entry.delete()
            return Response({"status": "removed", "wishlisted": False})

        Wishlist.objects.create(user=request.user, room=room)
        return Response(
            {"status": "added", "wishlisted": True},
            status=status.HTTP_201_CREATED,
        )
