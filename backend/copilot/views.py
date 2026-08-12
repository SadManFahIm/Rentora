from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from .serializers import CopilotChatRequestSerializer, CopilotChatResponseSerializer
from .services import chat


class CopilotRateThrottle(UserRateThrottle):
    """Copilot can be chatty, but it still talks to the search engine on
    every turn — a dedicated, generous-but-bounded scope beats an unbounded
    loop."""

    scope = "copilot"


class CopilotChatView(APIView):
    """Rentora Copilot — conversational room discovery.

    The core is deterministic + free: intent parsing (Bangla/English) feeds
    the existing search/ranking pipeline, and the response is generated over
    the *retrieved* listings only, so it can never invent a room, price or
    amenity. Public (like the rooms list) — no login required to chat.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [CopilotRateThrottle]

    @extend_schema(
        tags=["Copilot"],
        summary="Send a Copilot message",
        description=(
            "One conversational turn. Returns a structured reply: the rendered "
            "answer, the listings actually retrieved from the search engine, "
            "the interpreted intent (for UI chips), and suggested next steps. "
            "Echo back `session_id` to keep follow-up context (area/budget "
            "persist across turns)."
        ),
        request=CopilotChatRequestSerializer,
        responses=CopilotChatResponseSerializer,
    )
    def post(self, request):
        if not getattr(settings, "COPILOT_ENABLED", True):
            return Response(
                {"detail": "Copilot is currently disabled."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        request_serializer = CopilotChatRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.validated_data

        result = chat(
            message=data["message"],
            session_id=data.get("session_id") or None,
            user=getattr(request, "user", None),
        )
        return Response(CopilotChatResponseSerializer(result).data)
