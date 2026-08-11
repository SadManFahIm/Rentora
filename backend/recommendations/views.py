import logging

from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RecommendationSerializer
from .services.hybrid import get_hybrid_recommendations
from .services.similar import get_similar_rooms

logger = logging.getLogger(__name__)

CACHE_TIMEOUT_SECONDS = 60 * 60  # 1 hour
DEFAULT_LIMIT = 10


def _cache_key(user_id: int) -> str:
    return f"recommendations:user:{user_id}"


class RecommendationListView(APIView):
    """Personalized room recommendations: 60% content-based + 40%
    collaborative, falling back to popularity ranking for a user with no
    activity history yet. Result is cached per-user for an hour since
    building it means scoring every available room."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Recommendations"], summary="Get personalized room recommendations")
    def get(self, request):
        limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
        cache_key = _cache_key(request.user.id)

        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Recommendations cache hit for user %s", request.user.id)
            return Response(cached)

        logger.debug("Recommendations cache miss for user %s — computing", request.user.id)
        scored_rooms = get_hybrid_recommendations(request.user, limit=limit)

        payload = [
            {"room": sr.room, "match_score": sr.score, "match_reasons": sr.reasons}
            for sr in scored_rooms
        ]
        data = RecommendationSerializer(payload, many=True, context={"request": request}).data

        cache.set(cache_key, data, timeout=CACHE_TIMEOUT_SECONDS)
        return Response(data)


class SimilarRoomsView(APIView):
    """Content-based "similar rooms" for one listing (Phase 10).

    Reads are public (no auth) — the carousel appears on shared room links
    and for anonymous visitors too.
    """

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Recommendations"],
        summary="Similar rooms for a listing",
        description=(
            "Rooms most similar to the given room by area, type, price band "
            "and amenities, ranked by similarity score."
        ),
    )
    def get(self, request, room_id: int):
        from rooms.models import Room

        try:
            room = Room.objects.get(pk=room_id)
        except Room.DoesNotExist:
            raise NotFound("Room not found.") from None

        limit = int(request.query_params.get("limit", 8))
        scored_rooms = get_similar_rooms(room, limit=limit)
        payload = [
            {"room": sr.room, "match_score": sr.score, "match_reasons": sr.reasons}
            for sr in scored_rooms
        ]
        data = RecommendationSerializer(payload, many=True, context={"request": request}).data
        return Response(data)
