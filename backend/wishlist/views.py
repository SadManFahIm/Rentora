from django.shortcuts import get_object_or_404
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rooms.models import Room

from .models import Wishlist
from .serializers import WishlistSerializer


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
        return (
            Wishlist.objects.filter(user=self.request.user)
            .select_related("room", "room__owner")
            .prefetch_related("room__images")
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
