"""Price-anomaly badge for room cards (Phase 11+).

Reuses the existing pricing prediction engine (`pricing.services.prediction`)
— no second model. For each listing we compare the listed price against the
feature-based predicted fair price and, only when the prediction is confident
(`model_confidence == "high"`) and the gap clears `PRICE_ANOMALY_THRESHOLD`,
expose a neutral, transparent badge:

    {"available": true, "predicted_price": 12000, "difference_percentage": 25,
     "direction": "above_market", "badge": "25% above market"}

The list endpoint trains the Ridge model **once per request** and reuses it
for every room on the page (see the serializer field), so this never triggers
an N-per-room re-fit. Low-confidence predictions and sub-threshold gaps render
as `None` — no badge, no misleading valuation.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from .models import Room


def get_price_anomaly(room: Room, trained_model: Any | None = None) -> dict | None:
    """Return the anomaly badge payload for ``room``, or None.

    ``trained_model`` is an already-fitted ``TrainedModel`` (from
    ``pricing.services.prediction.train_price_model``) that the caller
    computed once for the whole request — pass None to train on demand.
    """
    if not getattr(settings, "PRICE_ANOMALY_ENABLED", True):
        return None

    from pricing.services.prediction import predict_price_from_model, train_price_model

    trained = trained_model if trained_model is not None else train_price_model()
    features = {
        "area": room.area,
        "room_type": room.room_type,
        "size_sqft": room.size_sqft,
        "amenities": room.amenities or [],
        "gender_preference": room.gender_preference,
    }
    prediction = predict_price_from_model(trained, features)
    if prediction.get("model_confidence") != "high":
        return None

    predicted = prediction.get("predicted_price")
    actual = float(room.price)
    if not predicted or predicted <= 0:
        return None

    difference = (actual - float(predicted)) / float(predicted)
    threshold = float(getattr(settings, "PRICE_ANOMALY_THRESHOLD", 0.20))
    if abs(difference) < threshold:
        return None

    percentage = abs(round(difference * 100))
    direction = "above_market" if difference > 0 else "below_market"
    return {
        "available": True,
        "predicted_price": round(float(predicted), 2),
        "difference_percentage": percentage,
        "direction": direction,
        "badge": f"{percentage}% {direction.replace('_', ' ')}",
    }
