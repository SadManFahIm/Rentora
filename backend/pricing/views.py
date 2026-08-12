from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from rooms.models import Room

from .models import MarketStat
from .serializers import (
    MarketStatSerializer,
    PriceInsightSerializer,
    PricePredictionRequestSerializer,
    PricePredictionSerializer,
    PricingSuggestionSerializer,
)
from .services.insight import get_price_insight
from .services.prediction import predict_fair_price
from .services.suggestion import get_pricing_suggestion


class PricePredictView(APIView):
    """Predict a fair price range for a listing that doesn't exist yet —
    the landlord-facing "what should I charge?" tool used while creating a
    new room, before there's a `Room` row (and therefore a price) to compare
    against the market at all.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Pricing"],
        summary="Predict a fair price for a new listing",
        description=(
            "Landlord-facing: given a prospective listing's area, room type, "
            "size, amenities and gender preference, returns a predicted fair "
            "price and a range around it, from a small Ridge regression "
            "trained on current listings (falls back to the overall market "
            "average when there isn't enough data yet)."
        ),
        request=PricePredictionRequestSerializer,
        responses=PricePredictionSerializer,
    )
    def post(self, request):
        request_serializer = PricePredictionRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        result = predict_fair_price(request_serializer.validated_data)
        return Response(PricePredictionSerializer(result).data)


class PriceInsightView(APIView):
    """Price insight for an existing, already-listed room — how its price
    compares to the current market for its (area, room_type) segment."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Pricing"],
        summary="Price insight for an existing room",
        description=(
            "Compares the room's price against its (area, room_type) market "
            "segment. Returns `null` if there isn't yet a market segment — "
            "or a big enough one — to compare it against."
        ),
        responses=PriceInsightSerializer,
    )
    def get(self, request, room_id):
        room = get_object_or_404(Room, pk=room_id)
        insight = get_price_insight(room)
        if insight is None:
            # DRF's `Response(None)` renders as an *empty* body, not the
            # JSON literal `null` — surprising for a client expecting
            # `response.json()` to always parse. `JsonResponse` doesn't
            # have that special case, so it's used here instead.
            return JsonResponse(None, safe=False)
        return Response(PriceInsightSerializer(insight).data)


class PricingSuggestionView(APIView):
    """AI pricing suggestion v2 for an **existing** listing — the landlord-
    facing "how much should I charge?" tool on the listing editor/dashboard.

    Owner or admin only (a pricing recommendation is the landlord's business
    data, not public). Extends the fair-price regression with demand,
    time-to-rent and confidence; the landlord explicitly applies it through
    the normal room update endpoint — nothing changes automatically.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Pricing"],
        summary="AI pricing suggestion for an existing listing",
        description=(
            "Landlord-facing: recommended price + range, demand score, estimated "
            "time-to-rent and confidence for one of the caller's own listings "
            "(admins may query any listing). Read-only — applying the price is "
            "a separate, explicit update."
        ),
        responses=PricingSuggestionSerializer,
    )
    def get(self, request, room_id):
        room = get_object_or_404(Room, pk=room_id)
        is_owner = room.owner_id == request.user.id
        is_admin = request.user.is_staff or request.user.role == request.user.Role.ADMIN
        if not (is_owner or is_admin):
            return Response(
                {"detail": "Only the listing owner or an admin can view the pricing suggestion."},
                status=status.HTTP_403_FORBIDDEN,
            )
        suggestion = get_pricing_suggestion(room)
        return Response(PricingSuggestionSerializer(suggestion).data)


class MarketStatsView(APIView):
    """Raw market stats, for dashboards/debugging — the same numbers
    `PriceInsightView` compares a room against, exposed directly."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Pricing"],
        summary="Raw market stats",
        description="Filter by `area` and/or `room_type`; omit both to list every computed segment.",
        responses=MarketStatSerializer,
    )
    def get(self, request):
        queryset = MarketStat.objects.all()

        area = request.query_params.get("area")
        if area:
            queryset = queryset.filter(area=area)

        room_type = request.query_params.get("room_type")
        if room_type:
            queryset = queryset.filter(room_type=room_type)

        return Response(MarketStatSerializer(queryset, many=True).data)
