from django.conf import settings
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from rooms.models import Room

from .serializers import (
    AgreementCheckRequestSerializer,
    CopilotChatRequestSerializer,
    CopilotChatResponseSerializer,
    CopilotListingFactsSerializer,
    CopilotShareSummarySerializer,
    LandlordCopilotRequestSerializer,
    NegotiationRequestSerializer,
    RentalAdviceRequestSerializer,
)
from .services import chat, listing_facts_for, share_summary_for


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
            listing_id=data.get("listing_id") or None,
        )
        return Response(CopilotChatResponseSerializer(result).data)


class CopilotListingFactsView(APIView):
    """Grounded fact card for one listing (Tier 3 RAG).

    Public — same fields the rooms list exposes. This is what the UI shows
    as the "Ask Copilot about this listing" panel and what grounds the
    listing chat mode. A listing that is unavailable is a 404, matching the
    rooms list's behaviour.
    """

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Copilot"],
        summary="Listing fact card (RAG source)",
        description=(
            "Grounded, public fact card for one listing — the retrieval "
            "document behind the listing chat mode. 404 when the listing is "
            "missing or unavailable."
        ),
        responses={200: CopilotListingFactsSerializer, 404: None},
    )
    def get(self, request, pk: int):
        facts = listing_facts_for(pk)
        if facts is None:
            raise Http404("Listing not found or unavailable")
        return Response(CopilotListingFactsSerializer(facts).data)


class CopilotShareSummaryView(APIView):
    """Share-ready AI summary for one listing (Phase 13 — WhatsApp reach).

    Public and deterministic: a compact one-liner built from the listing's
    public fields (price, area, type, size, amenities, verified state) that
    the UI pre-fills into the WhatsApp share message — every claim is a real
    listing field, so the share never exaggerates. 404 when the listing is
    missing or unavailable.
    """

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Copilot"],
        summary="Share-ready listing summary (WhatsApp)",
        description=(
            "A compact, deterministic summary of one listing used to pre-fill "
            "the WhatsApp share message. Grounded in the listing's public "
            "fields only — never invented. 404 when the listing is missing or "
            "unavailable."
        ),
        responses={200: CopilotShareSummarySerializer, 404: None},
    )
    def get(self, request, pk: int):
        summary = share_summary_for(pk)
        if summary is None:
            raise Http404("Listing not found or unavailable")
        return Response(summary)


class RentalAdvisorView(APIView):
    """AI Rental Advisor (Tier 4) — area recommendations grounded in market stats.

    Public (like the Copilot chat): takes a budget and returns affordable
    areas with real median rents, an affordability check and a move-in
    checklist. No login required — this is discovery, not account data.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [CopilotRateThrottle]

    @extend_schema(
        tags=["Copilot"],
        summary="Rental advisor — affordable areas for a budget",
        request=RentalAdviceRequestSerializer,
    )
    def post(self, request):
        serializer = RentalAdviceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .advisor import rental_advice

        result = rental_advice(**serializer.validated_data)
        return Response(result)


class NegotiationAssistantView(APIView):
    """AI Negotiation Assistant (Tier 4) — grounded counter-offer draft.

    Public for public listings: the draft quotes only the listing's own price
    and the area market (median/percentile-25), so the offer is a real,
    defensible number. Returns an EN + BN draft the user can copy.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [CopilotRateThrottle]

    @extend_schema(
        tags=["Copilot"],
        summary="Negotiation assistant — draft a grounded counter-offer",
        request=NegotiationRequestSerializer,
    )
    def post(self, request):
        serializer = NegotiationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .advisor import negotiation_draft

        try:
            room = Room.objects.get(pk=serializer.validated_data["listing_id"], is_available=True)
        except Room.DoesNotExist:
            raise Http404("Listing not found or unavailable") from None
        result = negotiation_draft(
            room,
            target_price=serializer.validated_data.get("target_price"),
            role=serializer.validated_data.get("role", "tenant"),
            tone=serializer.validated_data.get("tone", "polite"),
        )
        return Response(result)


class AgreementCheckerView(APIView):
    """AI Rental Agreement Checker (Tier 4) — first-pass clause review.

    Public: pastes agreement text, returns detected clauses with risk labels,
    missing clauses to ask about, and an honest disclaimer that this is not
    legal advice.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [CopilotRateThrottle]

    @extend_schema(
        tags=["Copilot"],
        summary="Agreement checker — first-pass clause risk review",
        request=AgreementCheckRequestSerializer,
    )
    def post(self, request):
        serializer = AgreementCheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .advisor import agreement_check

        return Response(agreement_check(serializer.validated_data["text"]))


class LandlordCopilotView(APIView):
    """Landlord Copilot (Tier 4) — grounded analysis of the caller's own listing.

    Authenticated + owner-scoped: the listing must belong to the requesting
    user (``owner``), otherwise 404 — a landlord can never ask about another
    landlord's room. Answers are built from the room's real booking/wishlist
    data and public market stats.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [CopilotRateThrottle]

    @extend_schema(
        tags=["Copilot"],
        summary="Landlord copilot — diagnose one of your listings",
        request=LandlordCopilotRequestSerializer,
    )
    def post(self, request):
        serializer = LandlordCopilotRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            room = Room.objects.get(
                pk=serializer.validated_data["listing_id"],
                owner=request.user,
            )
        except Room.DoesNotExist:
            raise Http404("Listing not found or not owned by you") from None
        from .advisor import landlord_insights

        return Response(landlord_insights(room))
