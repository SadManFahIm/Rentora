import logging

from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RecommendationSerializer
from .services.hybrid import get_hybrid_recommendations

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
