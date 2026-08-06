from __future__ import annotations

import os
import uuid

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from .models import ChatRoom, ChatRoomMembership, Message
from .presence import bulk_online_status
from .serializers import (
    ChatRoomSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from .utils import broadcast_message, broadcast_read_receipt

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
        description=(
            "Paginated messages (newest first). Marks the room read for the "
            "caller and broadcasts a read receipt. Supports `?search=` over "
            "message content."
        ),
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
    filter_backends = [SearchFilter]
    search_fields = ["content"]

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
            .prefetch_related("chat_room__memberships")
            .order_by("-created_at")
        )

    def list(self, request: Request, *args, **kwargs) -> Response:
        response = super().list(request, *args, **kwargs)
        # Mark the room read for this member now that they've fetched it, and
        # let any connected sockets know (mirrors what the WS consumer does
        # on connect / "mark_read").
        now = timezone.now()
        updated = ChatRoomMembership.objects.filter(
            chat_room_id=self.kwargs["room_id"], user=request.user
        ).update(last_read_at=now)
        if updated:
            broadcast_read_receipt(self.kwargs["room_id"], request.user.pk, now)
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


@extend_schema(
    tags=["Chat"],
    summary="Bulk online status",
    description=(
        "Given a list of user ids (as `user_ids` in the JSON body, or a "
        "comma-separated `?user_ids=` query param), returns which are "
        "currently online."
    ),
    examples=[
        OpenApiExample("Request body", value={"user_ids": [1, 2, 3]}, request_only=True),
        OpenApiExample("Response", value={"online": [1, 3], "offline": [2]}, response_only=True),
    ],
)
class OnlineStatusView(APIView):
    """GET /api/v1/chat/online-status/ — who among `user_ids` is online now."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, *args, **kwargs) -> Response:
        raw_ids = self._extract_user_ids(request)
        try:
            user_ids = [int(v) for v in raw_ids]
        except (TypeError, ValueError):
            return Response(
                {"detail": "user_ids must be a list of integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_ids:
            return Response({"online": [], "offline": []})

        return Response(bulk_online_status(user_ids))

    @staticmethod
    def _extract_user_ids(request: Request) -> list:
        """Accept `user_ids` from the JSON body (as the task specifies) or,
        since a GET request body is non-standard and not every client sends
        one, fall back to a `?user_ids=1,2,3` query param."""
        body_ids = request.data.get("user_ids") if hasattr(request, "data") else None
        if body_ids:
            return body_ids

        query_ids = request.query_params.get("user_ids", "")
        return [v for v in query_ids.split(",") if v]


class ChatUploadRateThrottle(UserRateThrottle):
    """Uploads are costlier than a normal API call — throttled tighter than
    the general 'user' rate. Scope rate lives in DEFAULT_THROTTLE_RATES."""

    scope = "chat_upload"


# Deliberately an allow-list, not a deny-list: only formats the frontend
# actually needs to render/preview are accepted.
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_ALLOWED_FILE_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "application/zip",
} | _ALLOWED_IMAGE_TYPES
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


@extend_schema(
    tags=["Chat"],
    summary="Upload a chat attachment",
    description=(
        "Multipart upload (field name `file`). Saves to media/chat/ and "
        "returns the file's URL plus the inferred `message_type` "
        "('image' or 'file') to use when sending the actual chat message."
    ),
)
class ChatUploadView(APIView):
    """POST /api/v1/chat/upload/ — store a file, return its URL for use in a message."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]
    throttle_classes = [ChatUploadRateThrottle]

    def post(self, request: Request, *args, **kwargs) -> Response:
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        if uploaded.size > _MAX_UPLOAD_SIZE:
            return Response(
                {"detail": f"File too large. Maximum size is {_MAX_UPLOAD_SIZE // (1024 * 1024)}MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = uploaded.content_type or ""
        if content_type not in _ALLOWED_FILE_TYPES:
            return Response(
                {"detail": f"Unsupported file type: {content_type or 'unknown'}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message_type = (
            Message.MessageType.IMAGE
            if content_type in _ALLOWED_IMAGE_TYPES
            else Message.MessageType.FILE
        )

        # Random filename: avoids collisions and never trusts the client's
        # original name (path traversal / info leakage).
        ext = os.path.splitext(uploaded.name)[1][:10]
        saved_path = default_storage.save(f"chat/{uuid.uuid4().hex}{ext}", uploaded)
        file_url = request.build_absolute_uri(default_storage.url(saved_path))

        return Response(
            {"file_url": file_url, "message_type": message_type},
            status=status.HTTP_201_CREATED,
        )
