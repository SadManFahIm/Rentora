from rest_framework import serializers

from rooms.models import Room

from .models import MarketStat


class MarketStatSerializer(serializers.ModelSerializer):
    """Read-only representation of a computed market segment snapshot."""

    class Meta:
        model = MarketStat
        fields = [
            "area",
            "room_type",
            "avg_price",
            "median_price",
            "min_price",
            "max_price",
            "percentile_25",
            "percentile_75",
            "sample_size",
            "calculated_at",
        ]
        read_only_fields = fields


class PriceInsightSerializer(serializers.Serializer):
    """A room's price compared against its (area, room_type) market segment.

    Not a ModelSerializer — this wraps the computed result of
    `pricing.services.insight.get_price_insight`, not a persisted model
    instance.
    """

    avg_price = serializers.FloatField(help_text="Market segment average price.")
    your_price = serializers.FloatField()
    percentage_diff = serializers.FloatField(help_text="Signed % difference from the segment average.")
    classification = serializers.ChoiceField(
        choices=["great_deal", "good_price", "fair_price", "above_average", "overpriced"]
    )
    message = serializers.CharField()
    sample_size = serializers.IntegerField(help_text="Rooms the segment average was built from.")


class PricePredictionRequestSerializer(serializers.Serializer):
    """Input for POST /pricing/predict/ — describes a not-yet-created
    listing a landlord wants a fair-price estimate for."""

    area = serializers.ChoiceField(choices=Room.Area.choices)
    room_type = serializers.ChoiceField(choices=Room.RoomType.choices)
    size_sqft = serializers.IntegerField(min_value=1)
    amenities = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    gender_preference = serializers.ChoiceField(
        choices=Room.GenderPreference.choices, required=False, default=Room.GenderPreference.ANY
    )


class PricePredictionSerializer(serializers.Serializer):
    """Not a ModelSerializer — wraps the computed result of
    `pricing.services.prediction.predict_fair_price`."""

    predicted_price = serializers.FloatField(allow_null=True)
    price_range_low = serializers.FloatField(allow_null=True)
    price_range_high = serializers.FloatField(allow_null=True)
    model_confidence = serializers.ChoiceField(choices=["high", "low", "none"])
    explanation = serializers.CharField(help_text="Plain-English reason for the estimate, for a non-technical landlord.")
