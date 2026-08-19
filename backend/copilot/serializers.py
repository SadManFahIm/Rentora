from rest_framework import serializers


class CopilotChatRequestSerializer(serializers.Serializer):
    """One Copilot turn. ``session_id`` is optional — omit it to start a new
    conversation (the response returns one to echo back for follow-ups)."""

    message = serializers.CharField(
        min_length=1, max_length=500, help_text="Free-text request, Bangla or English."
    )
    session_id = serializers.CharField(required=False, allow_blank=True, default="")
    listing_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="When set, the turn is grounded on this single listing (RAG over one document).",
    )


class CopilotIntentSerializer(serializers.Serializer):
    budget_max = serializers.IntegerField(allow_null=True)
    areas = serializers.ListField(child=serializers.CharField())
    room_type = serializers.CharField(allow_null=True)
    gender = serializers.CharField(allow_null=True)
    months = serializers.ListField(child=serializers.CharField())
    amenities = serializers.ListField(child=serializers.CharField())
    property_words = serializers.ListField(child=serializers.CharField())
    hints = serializers.ListField(child=serializers.CharField())


class CopilotListingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    price = serializers.FloatField()
    area = serializers.CharField()
    room_type = serializers.CharField()
    amenities = serializers.ListField(child=serializers.CharField())
    verified = serializers.BooleanField()
    tier = serializers.CharField()
    image = serializers.CharField(allow_null=True)


class RentalAdviceRequestSerializer(serializers.Serializer):
    """AI Rental Advisor input — budget is required, everything else optional."""

    budget_max = serializers.FloatField(min_value=0)
    room_type = serializers.CharField(required=False, default="single")
    area = serializers.CharField(required=False, allow_blank=True, default="")
    monthly_income = serializers.FloatField(required=False, allow_null=True, default=None)


class NegotiationRequestSerializer(serializers.Serializer):
    """AI Negotiation Assistant input — listing + optional target price/role."""

    listing_id = serializers.IntegerField()
    target_price = serializers.FloatField(required=False, allow_null=True, default=None)
    role = serializers.ChoiceField(choices=["tenant", "landlord"], default="tenant")
    tone = serializers.ChoiceField(choices=["polite", "friendly", "formal"], default="polite")


class AgreementCheckRequestSerializer(serializers.Serializer):
    """AI Rental Agreement Checker input — paste the agreement text."""

    text = serializers.CharField(min_length=10, max_length=20000)


class SupportRequestSerializer(serializers.Serializer):
    """AI Support Copilot input — a free-text help question (EN or BN)."""

    message = serializers.CharField(min_length=1, max_length=500)


class LandlordCopilotRequestSerializer(serializers.Serializer):
    """Landlord Copilot input — a listing id the caller owns."""

    listing_id = serializers.IntegerField()


class CopilotListingFactsSerializer(serializers.Serializer):
    """Full grounded fact card for one listing (Tier 3 RAG). Public fields
    only — the same data the rooms list exposes, plus deterministic map
    intel. Never includes owner contact details or internal scores."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    price = serializers.FloatField()
    area = serializers.CharField()
    area_display = serializers.CharField()
    room_type = serializers.CharField()
    room_type_display = serializers.CharField()
    gender_preference = serializers.CharField()
    size_sqft = serializers.IntegerField(allow_null=True)
    amenities = serializers.ListField(child=serializers.CharField())
    verified = serializers.BooleanField()
    available = serializers.BooleanField()
    address = serializers.CharField()
    description = serializers.CharField()
    metro_km = serializers.FloatField(allow_null=True)
    image = serializers.CharField(allow_null=True)


class CopilotShareSummarySerializer(serializers.Serializer):
    """Compact share-ready summary (Phase 13). Public fields only."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    price = serializers.FloatField()
    area = serializers.CharField()
    area_display = serializers.CharField()
    summary = serializers.CharField()


class CopilotChatResponseSerializer(serializers.Serializer):
    """Structured Copilot reply: a human message plus the *retrieved* rooms
    and the interpreted intent (chips) so the UI never parses prose.

    ``mode`` is ``"search"`` (rooms retrieved from the engine) or
    ``"listing"`` (grounded on one listing — ``listing`` carries its fact
    card and ``aspect`` says which question was answered)."""

    session_id = serializers.CharField()
    message = serializers.CharField()
    intent = CopilotIntentSerializer()
    listings = CopilotListingSerializer(many=True)
    total_count = serializers.IntegerField()
    suggestions = serializers.ListField(child=serializers.CharField())
    mode = serializers.CharField(required=False, default="search")
    listing = CopilotListingFactsSerializer(allow_null=True, required=False)
    aspect = serializers.CharField(allow_null=True, required=False)
