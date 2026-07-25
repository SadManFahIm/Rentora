from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from .models import ChatRoom, ChatRoomMembership, Message
from .serializers import (
    ChatRoomSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from .utils import broadcast_message

User = get_user_model()


@extend_schema_view(
    list=extend_schema(tags=["Chat"], summary="List my chat rooms"),
    retrieve=extend_schema(tags=["Chat"], summary="Retrieve a chat room"),
    create=extend_schema(
        tags=["Chat"],
        summary="Start (or fetch) a direct chat",
        description=(
            "Create a direct chat with another user. If a direct chat between "
            "the two users already exists it is returned instead of creating a "
            "duplicate. Optionally link it to a room listing."
        ),
        examples=[
            OpenApiExample(
                "Direct chat",
                value={"user_id": 2, "listing_id": 1},
                request_only=True,
            )
        ],
    ),
)
class ChatRoomViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Chat rooms the authenticated user is a member of."""

    serializer_class = ChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ChatRoom.objects.none()
        return (
            ChatRoom.objects.filter(members=self.request.user)
            .select_related("listing")
            .prefetch_related("members", "memberships", "messages")
            .distinct()
        )

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Start a direct chat with ``user_id`` (idempotent per user pair)."""
        user_id = request.data.get("user_id")
        if user_id is None:
            return Response(
                {"detail": "user_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if str(user_id) == str(request.user.pk):
            return Response(
                {"detail": "You cannot start a chat with yourself."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        other = get_object_or_404(User, pk=user_id)

        listing = None
        listing_id = request.data.get("listing_id")
        if listing_id is not None:
            from rooms.models import Room

            listing = get_object_or_404(Room, pk=listing_id)

        room = self._get_or_create_direct_room(request.user, other, listing)
        serializer = self.get_serializer(room)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _get_or_create_direct_room(user, other, listing) -> ChatRoom:
        """Return the existing 1:1 direct room for the pair, or create one."""
        existing = (
            ChatRoom.objects.filter(room_type=ChatRoom.RoomType.DIRECT, members=user)
            .filter(members=other)
            .first()
        )
        if existing is not None:
            if listing is not None and existing.listing_id is None:
                existing.listing = listing
                existing.save(update_fields=["listing"])
            return existing

        room = ChatRoom.objects.create(
            room_type=ChatRoom.RoomType.DIRECT, listing=listing
        )
        ChatRoomMembership.objects.bulk_create(
            [
                ChatRoomMembership(chat_room=room, user=user),
                ChatRoomMembership(chat_room=room, user=other),
            ]
        )
        return room


@extend_schema_view(
    list=extend_schema(
        tags=["Chat"],
        summary="List messages in a room",
        description="Paginated messages (newest first). Marks the room read for the caller.",
    ),
    create=extend_schema(
        tags=["Chat"],
        summary="Send a message (REST fallback)",
        description="Persist a message and broadcast it to the room's WebSocket group.",
    ),
)
class MessageViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Messages for a single chat room (nested under /chat/rooms/:room_id/)."""

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return MessageCreateSerializer if self.action == "create" else MessageSerializer

    def get_chat_room(self) -> ChatRoom:
        """Resolve the room from the URL, enforcing membership (404 otherwise)."""
        return get_object_or_404(
            ChatRoom, pk=self.kwargs["room_id"], members=self.request.user
        )

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Message.objects.none()
        room = self.get_chat_room()
        return (
            Message.objects.filter(chat_room=room)
            .select_related("sender")
            .order_by("-created_at")
        )

    def list(self, request: Request, *args, **kwargs) -> Response:
        response = super().list(request, *args, **kwargs)
        # Mark the room read for this member now that they've fetched it.
        ChatRoomMembership.objects.filter(
            chat_room_id=self.kwargs["room_id"], user=request.user
        ).update(last_read_at=timezone.now())
        return response

    def create(self, request: Request, *args, **kwargs) -> Response:
        room = self.get_chat_room()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(chat_room=room, sender=request.user)

        # Bump room ordering and broadcast to any connected sockets.
        room.save(update_fields=["updated_at"])
        payload = MessageSerializer(message, context=self.get_serializer_context()).data
        broadcast_message(room.pk, payload)

        return Response(payload, status=status.HTTP_201_CREATED)
