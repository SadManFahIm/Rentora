from __future__ import annotations

import logging
import os
import uuid

logger = logging.getLogger(__name__)

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

from .antivirus import scan_bytes
from .models import ChatRoom, ChatRoomMembership, ChatSafetyEvent, Message, Report, UserBlock
from .presence import bulk_online_status
from .safety import record_safety_event, run_chat_safety, safety_payload
from .serializers import (
    ChatRoomSerializer,
    ChatSafetyEventSerializer,
    MessageCreateSerializer,
    MessageEditSerializer,
    MessageSerializer,
    ReportActionSerializer,
    ReportCreateSerializer,
    ReportSerializer,
)
from .utils import (
    blocked_with_any,
    broadcast_message,
    broadcast_message_delete,
    broadcast_message_update,
    broadcast_read_receipt,
    is_blocked_between,
)

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

        # Block enforcement (Phase 12.4): blocked pairs can't open new chats.
        if is_blocked_between(request.user, other):
            return Response(
                {"detail": "You can't start a conversation with this user."},
                status=status.HTTP_403_FORBIDDEN,
            )

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

        room = ChatRoom.objects.create(room_type=ChatRoom.RoomType.DIRECT, listing=listing)
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
    partial_update=extend_schema(
        tags=["Chat"],
        summary="Edit a message",
        description=(
            "Sender only. Replaces the content of one of your own text "
            "messages; the edit runs through the chat-safety engine again and "
            "is written to the audit log. The other participant sees the "
            "updated message in real time via WebSocket."
        ),
        request=MessageEditSerializer,
        responses=MessageSerializer,
    ),
    destroy=extend_schema(
        tags=["Chat"],
        summary="Delete a message",
        description=(
            "Sender only. Soft-delete: the content is replaced with a generic "
            "notice and the message is excluded from search, but the thread "
            "keeps its shape. Audited as `chat.message.deleted`."
        ),
    ),
)
class MessageViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.UpdateModelMixin,
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
        return get_object_or_404(ChatRoom, pk=self.kwargs["room_id"], members=self.request.user)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Message.objects.none()
        room = self.get_chat_room()
        queryset = (
            Message.objects.filter(chat_room=room)
            .select_related("sender")
            .prefetch_related("chat_room__memberships")
            .order_by("-created_at")
        )
        # Deleted messages stay in the thread (the row keeps its slot) but
        # are excluded from search — their content is a generic notice, so
        # matching it would only surface noise.
        if self.request.query_params.get("search"):
            queryset = queryset.filter(is_deleted=False)
        return queryset

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

        # Block enforcement (Phase 12.4): a conversation closed by a block is
        # closed for both sides — no messages either way.
        if blocked_with_any(request.user, room):
            return Response(
                {"detail": "You can't send messages in this conversation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Chat Safety Engine (Phase 12.3): assess the outgoing message and
        # apply the configured policy before anything is stored. A blocked
        # message is stored as the safety notice — the sender's raw text is
        # never persisted or broadcast.
        content = serializer.validated_data.get("content", "")
        final_content, assessment, outcome = run_chat_safety(content, room, request.user)
        message = serializer.save(chat_room=room, sender=request.user, content=final_content)
        record_safety_event(room, request.user, message, assessment, outcome)

        # Bump room ordering and broadcast to any connected sockets.
        room.save(update_fields=["updated_at"])
        payload = MessageSerializer(message, context=self.get_serializer_context()).data
        payload["safety"] = safety_payload(assessment, outcome)
        broadcast_message(room.pk, payload)

        return Response(payload, status=status.HTTP_201_CREATED)

    def _get_editable_message(self, request: Request, pk: int) -> Message:
        """Resolve a message in the caller's room and enforce sender-only
        edit/delete. Shared by ``partial_update`` and ``destroy``."""
        room = self.get_chat_room()
        message = get_object_or_404(Message, pk=pk, chat_room=room)
        if message.sender_id != request.user.pk:
            raise PermissionError("You can only modify your own messages.")
        return message

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """Sender-only edit. The new text re-runs through the chat-safety
        engine (an edit is still a new message), the change is audited, and
        connected sockets get the updated message in place."""
        try:
            message = self._get_editable_message(request, kwargs["pk"])
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        if message.message_type != Message.MessageType.TEXT:
            return Response(
                {"detail": "Only text messages can be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if message.is_deleted:
            return Response(
                {"detail": "This message was deleted and cannot be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = MessageEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        room = self.get_chat_room()
        new_content = serializer.validated_data["content"]
        final_content, assessment, outcome = run_chat_safety(new_content, room, request.user)
        message.content = final_content
        message.edited_at = timezone.now()
        message.save(update_fields=["content", "edited_at"])
        record_safety_event(room, request.user, message, assessment, outcome)

        from audit.services import log_action

        log_action(
            actor=request.user,
            action="chat.message.edited",
            target=message,
            request=request,
            detail={"message_id": message.pk, "room_id": room.pk},
        )

        payload = MessageSerializer(message, context=self.get_serializer_context()).data
        payload["safety"] = safety_payload(assessment, outcome)
        broadcast_message_update(room.pk, payload)
        return Response(payload)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Sender-only soft-delete: content is replaced with a generic notice,
        ``is_deleted`` flips, the change is audited, and connected sockets see
        the deleted state. Idempotent — deleting twice is a no-op."""
        try:
            message = self._get_editable_message(request, kwargs["pk"])
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        if message.is_deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)

        message.content = "[Message deleted]"
        message.is_deleted = True
        message.edited_at = timezone.now()
        message.save(update_fields=["content", "is_deleted", "edited_at"])

        from audit.services import log_action

        log_action(
            actor=request.user,
            action="chat.message.deleted",
            target=message,
            request=request,
            detail={"message_id": message.pk, "room_id": message.chat_room_id},
        )

        payload = MessageSerializer(message, context=self.get_serializer_context()).data
        broadcast_message_delete(message.chat_room_id, payload)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
                {
                    "detail": f"File too large. Maximum size is {_MAX_UPLOAD_SIZE // (1024 * 1024)}MB."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = uploaded.content_type or ""
        if content_type not in _ALLOWED_FILE_TYPES:
            return Response(
                {"detail": f"Unsupported file type: {content_type or 'unknown'}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Virus scan (Tier 2, optional): when ClamAV is enabled and reachable,
        # a positive detection rejects the file outright. When no scanner is
        # available the result is always clean-by-default — the type/size
        # checks above remain the baseline gate either way.
        uploaded.seek(0)
        scan = scan_bytes(uploaded.read())
        uploaded.seek(0)
        if scan.rejected:
            logger.warning(
                "chat upload rejected by virus scan: user=%s size=%s viruses=%s",
                request.user.pk,
                uploaded.size,
                scan.viruses,
            )
            return Response(
                {"detail": "File rejected by the security scan."},
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


class ChatSafetyEventsView(APIView):
    """Admin-only feed of chat-safety events (Phase 12.3).

    Every warned/flagged/blocked message assessment, newest first, with the
    metadata the engine recorded (detector keys, risk, outcome) — never the
    message content. Powers the trust & safety moderation queue.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Chat"],
        summary="List chat safety events",
        description="Admin only. Recent chat-safety assessments (metadata only — "
        "never message content), newest first, at most 100.",
        responses=ChatSafetyEventSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        if not (request.user.is_staff or request.user.role == "admin"):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        events = ChatSafetyEvent.objects.select_related("sender", "chat_room").order_by(
            "-created_at"
        )[:100]
        return Response(ChatSafetyEventSerializer(events, many=True).data)


# ============================================================
# Report / block (Phase 12.4)
# ============================================================


def _is_admin_user(user) -> bool:
    return user.is_staff or user.role == "admin"


class ReportRateThrottle(UserRateThrottle):
    """Reports are moderation actions — a dedicated scope stops one user from
    flooding the admin queue with reports (of the same or many targets). Rate
    lives in ``DEFAULT_THROTTLE_RATES['report']``; ``get_rate`` reads the live
    ``api_settings`` so tests can override it without a stale import-time
    snapshot (same pattern as config.throttling.AuthRateThrottle)."""

    scope = "report"

    def get_rate(self):
        from rest_framework.settings import api_settings

        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]


class ReportCreateView(APIView):
    """Report a user and/or a specific message (Phase 12.4).

    Categories cover the marketplace's trust risks: scam, harassment, fake
    listing, payment fraud (a suspicious payment request), impersonation,
    spam, other. Reports land in the admin moderation queue.

    Abuse guard (Tier-1 quick win): reports are rate-limited per user, and a
    duplicate report of the same target (same message, while an earlier
    report is still open/under-review/escalated) returns the existing report
    instead of creating a new one — so a user can't stack the queue with
    repeats, while a fresh report after a resolution is still allowed.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ReportRateThrottle]

    @extend_schema(
        tags=["Chat"],
        summary="Report a user or message",
        description=(
            "Authenticated. Reports another user (and optionally a specific "
            "message, e.g. a suspicious payment request) for moderation."
        ),
        request=ReportCreateSerializer,
        responses=ReportSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = ReportCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        target_user = get_object_or_404(User, pk=serializer.validated_data["target_user_id"])
        message = None
        message_id = serializer.validated_data.get("message_id")
        if message_id is not None:
            message = get_object_or_404(Message, pk=message_id)
            if message.sender_id != target_user.pk:
                return Response(
                    {"detail": "The reported message is not from the reported user."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Duplicate-report guard: while an earlier report of the same target
        # (and same message, when one was given) is still open or under
        # review, a repeat returns the existing ticket instead of stacking a
        # duplicate on the queue. A resolved/dismissed report does not block
        # a new report — the user may legitimately report again.
        active = [Report.Status.OPEN, Report.Status.UNDER_REVIEW, Report.Status.ESCALATED]
        existing = (
            Report.objects.filter(
                reporter=request.user,
                target_user=target_user,
                status__in=active,
            )
            .filter(message=message if message is not None else None)
            .first()
        )
        if existing is not None:
            data = ReportSerializer(existing).data
            data["duplicate"] = True
            return Response(data, status=status.HTTP_200_OK)

        report = Report.objects.create(
            reporter=request.user,
            target_user=target_user,
            message=message,
            category=serializer.validated_data["category"],
            description=serializer.validated_data.get("description", ""),
        )
        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)


class ReportListView(APIView):
    """Admin moderation queue for user/message reports."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Chat"],
        summary="List reports",
        description="Admin only. Reports, newest first. `?status=open` filters to "
        "unresolved reports (default).",
        responses=ReportSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        if not _is_admin_user(request.user):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        status_filter = request.query_params.get("status", "open")
        queryset = Report.objects.select_related("reporter", "target_user", "message")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return Response(ReportSerializer(queryset[:100], many=True).data)


class ReportActionView(APIView):
    """Admin decision on a report. Every action is audited (``report.*``);
    warn/suspend also notify the reported user, and the reporter is notified
    of the outcome either way."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Chat"],
        summary="Act on a report",
        description="Admin only. `action`: dismiss | warn | suspend | escalate.",
        request=ReportActionSerializer,
        responses=ReportSerializer,
    )
    def post(self, request: Request, report_id: int) -> Response:
        if not _is_admin_user(request.user):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ReportActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = get_object_or_404(Report, pk=report_id)
        action = serializer.validated_data["action"]
        note = serializer.validated_data.get("note", "")

        from django.db import transaction

        from audit.services import log_action
        from notifications.models import Notification
        from notifications.utils import create_notification

        with transaction.atomic():
            if action == "dismiss":
                report.status = Report.Status.DISMISSED
                report.action_taken = Report.Action.DISMISS
            elif action == "escalate":
                report.status = Report.Status.ESCALATED
                report.action_taken = Report.Action.ESCALATE
            elif action == "warn":
                report.status = Report.Status.RESOLVED
                report.action_taken = Report.Action.WARN
                create_notification(
                    user=report.target_user,
                    notification_type=Notification.Type.ACCOUNT_WARNING,
                    title="⚠️ You received a warning",
                    message=note or "A report against you was reviewed and a warning was issued.",
                    action_url="/dashboard",
                )
            elif action == "suspend":
                report.status = Report.Status.RESOLVED
                report.action_taken = Report.Action.SUSPEND
                report.target_user.is_active = False
                report.target_user.save(update_fields=["is_active"])
                create_notification(
                    user=report.target_user,
                    notification_type=Notification.Type.ACCOUNT_SUSPENDED,
                    title="🚫 Account suspended",
                    message=note or "Your account was suspended following a review.",
                    action_url="/auth",
                )

            report.admin_note = note
            report.resolved_at = timezone.now()
            report.save()

            log_action(
                actor=request.user,
                action=f"report.{action}",
                target=report,
                request=request,
                detail={
                    "note": note,
                    "report_id": report.pk,
                    "category": report.category,
                    "target_user_id": report.target_user_id,
                    "reporter_id": report.reporter_id,
                },
            )

            # The reporter always learns the outcome of their report.
            create_notification(
                user=report.reporter,
                notification_type=Notification.Type.REPORT_RESOLVED,
                title="Report resolved",
                message=(
                    f"Your {report.get_category_display()} report was {action}d."
                    if action != "suspend"
                    else f"Your {report.get_category_display()} report was actioned."
                ),
                action_url="/dashboard",
            )
        return Response(ReportSerializer(report).data)


class BlockUserView(APIView):
    """Block another user (Phase 12.4). Idempotent — blocking someone already
    blocked is a no-op that returns the existing block."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Chat"],
        summary="Block a user",
        description="Authenticated. `user_id`: the user to block. Idempotent.",
    )
    def post(self, request: Request) -> Response:
        user_id = request.data.get("user_id")
        if user_id is None:
            return Response({"detail": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if str(user_id) == str(request.user.pk):
            return Response(
                {"detail": "You cannot block yourself."}, status=status.HTTP_400_BAD_REQUEST
            )
        target = get_object_or_404(User, pk=user_id)
        UserBlock.objects.get_or_create(blocker=request.user, blocked=target)
        return Response({"detail": f"{target.username} is now blocked."}, status=status.HTTP_200_OK)


class UnblockUserView(APIView):
    """Unblock a user (Phase 12.4). Only the blocker can unblock; the blocked
    user cannot re-open the channel themselves."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Chat"], summary="Unblock a user", description="Authenticated.")
    def delete(self, request: Request, user_id: int) -> Response:
        deleted, _ = UserBlock.objects.filter(blocker=request.user, blocked_id=user_id).delete()
        if not deleted:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BlockedUsersView(APIView):
    """The caller's list of blocked users (Phase 12.4)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Chat"],
        summary="List blocked users",
        description="Authenticated. The caller's blocked users, with usernames.",
    )
    def get(self, request: Request) -> Response:
        blocks = UserBlock.objects.filter(blocker=request.user).select_related("blocked")
        return Response([{"id": b.blocked_id, "username": b.blocked.username} for b in blocks])
