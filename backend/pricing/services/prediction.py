"""Fair-price prediction: a small, explainable linear model trained
on-the-fly from the current room listings.

The dataset here is tiny (dozens of rooms, not thousands), so this
deliberately avoids anything that could overfit or turn into a black box:

- **Ridge regression** (L2-regularized linear regression), not a deep model
  — every prediction is a weighted sum of a handful of plain, named
  features, and Ridge's regularization keeps one unusual listing from
  swinging the model's coefficients too far, which matters a lot with only
  dozens of training rows.
- **Retrained from scratch on every call**, not persisted to disk. With
  well under 100 rooms, training takes milliseconds, so there's no real
  cost to always training on the freshest data — and no risk of a
  joblib-persisted model file silently going stale as listings change.

Features (all plain and named, never hashed/embedded, so a coefficient can
always be traced back to something a landlord would recognise): area
(one-hot), room_type (one-hot), gender_preference (one-hot), size_sqft,
amenities_count, has_ac.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from django.db.models import Avg
from sklearn.linear_model import Ridge

from rooms.models import Room

# Below this many available rooms — either on the whole platform, or in the
# specific area a prediction is requested for — a regression's coefficients
# aren't trustworthy: fall back to a plain market average instead of a
# specific-looking but noisy number.
MIN_ROOMS = 10

RIDGE_ALPHA = 1.0

AREAS = list(Room.Area.values)
ROOM_TYPES = list(Room.RoomType.values)
GENDER_PREFERENCES = list(Room.GenderPreference.values)


def _has_ac(amenities: list[str]) -> bool:
    return any(str(a).strip().lower() == "ac" for a in amenities or [])


def _feature_vector(
    *,
    area: str,
    room_type: str,
    gender_preference: str,
    size_sqft: float,
    amenities: list[str] | None,
) -> list[float]:
    """Build one room's feature row. Every position is a plain, named
    quantity (a one-hot flag or a raw count) — no hashing or embeddings —
    so a fitted coefficient can always be explained in plain English."""
    amenities = amenities or []
    return [
        *(1.0 if area == a else 0.0 for a in AREAS),
        *(1.0 if room_type == t else 0.0 for t in ROOM_TYPES),
        *(1.0 if gender_preference == g else 0.0 for g in GENDER_PREFERENCES),
        float(size_sqft),
        float(len(amenities)),
        1.0 if _has_ac(amenities) else 0.0,
    ]


@dataclass
class TrainedModel:
    model: Ridge
    residual_std: float
    n_samples: int


def train_price_model() -> TrainedModel | None:
    """Train a fresh Ridge regression on every currently-available room.

    Returns None if there isn't enough data on the platform at all (see
    MIN_ROOMS) — the caller should fall back to a plain market-average
    estimate rather than trust a model fit on a handful of rows.
    """
    rooms = list(Room.objects.filter(is_available=True))
    if len(rooms) < MIN_ROOMS:
        return None

    X = np.array(
        [
            _feature_vector(
                area=r.area,
                room_type=r.room_type,
                gender_preference=r.gender_preference,
                size_sqft=r.size_sqft,
                amenities=r.amenities,
            )
            for r in rooms
        ]
    )
    y = np.array([float(r.price) for r in rooms])

    model = Ridge(alpha=RIDGE_ALPHA)
    model.fit(X, y)

    residuals = y - model.predict(X)
    # The residual spread becomes the ± margin around a prediction — a model
    # that fits the training data tightly gets a tight range; one with a lot
    # of unexplained variation gets an honestly wider one.
    residual_std = float(np.std(residuals)) if len(residuals) > 1 else float(np.mean(y)) * 0.1

    return TrainedModel(model=model, residual_std=residual_std, n_samples=len(rooms))


def predict_price_from_model(trained: TrainedModel, features: dict[str, Any]) -> dict[str, Any]:
    """Predict from an **already-trained** model — the caller may train once
    (``train_price_model``) and score many listings without re-fitting, which
    is what the price-anomaly badge does on the room list endpoint.

    Returns the same shape as ``predict_fair_price``; ``model_confidence`` is
    ``"high"`` when the model exists and the requested area has enough data.
    """
    area = features["area"]
    room_type = features["room_type"]
    size_sqft = features["size_sqft"]
    amenities = features.get("amenities") or []
    gender_preference = features.get("gender_preference") or Room.GenderPreference.ANY

    area_room_count = Room.objects.filter(is_available=True, area=area).count()
    if trained is None or area_room_count < MIN_ROOMS:
        avg_price = Room.objects.filter(is_available=True).aggregate(avg=Avg("price"))["avg"]
        if avg_price is None:
            return {
                "predicted_price": None,
                "price_range_low": None,
                "price_range_high": None,
                "model_confidence": "none",
                "explanation": "Not enough listings on the platform yet to estimate a fair price.",
            }

        avg_price = float(avg_price)
        margin = avg_price * 0.2
        reason = (
            "Not enough listings on the platform yet to train a price model"
            if trained is None
            else f"Fewer than {MIN_ROOMS} listings in {area} yet"
        )
        return {
            "predicted_price": round(avg_price, 2),
            "price_range_low": round(max(avg_price - margin, 0), 2),
            "price_range_high": round(avg_price + margin, 2),
            "model_confidence": "low",
            "explanation": f"{reason}, so this is the overall market average rather than a feature-based prediction.",
        }

    vector = np.array(
        [
            _feature_vector(
                area=area,
                room_type=room_type,
                gender_preference=gender_preference,
                size_sqft=size_sqft,
                amenities=amenities,
            )
        ]
    )
    predicted = max(float(trained.model.predict(vector)[0]), 0.0)
    margin = trained.residual_std if trained.residual_std > 0 else predicted * 0.15

    explanation_bits = [f"Based on {trained.n_samples} comparable listings across the platform"]
    if _has_ac(amenities):
        explanation_bits.append("AC availability was factored into the estimate")

    return {
        "predicted_price": round(predicted, 2),
        "price_range_low": round(max(predicted - margin, 0), 2),
        "price_range_high": round(predicted + margin, 2),
        "model_confidence": "high",
        "explanation": "; ".join(explanation_bits) + ".",
    }


def predict_fair_price(features: dict[str, Any]) -> dict[str, Any]:
    """Predict a fair price range for a *new* listing described by
    `features` (area, room_type, size_sqft, amenities, gender_preference).

    Always returns a usable range. Falls back to the overall market average
    (flagged `model_confidence="low"`) when there isn't enough data on the
    platform to train a model at all, or when the requested area specifically
    has fewer than MIN_ROOMS listings — the model may exist, but it has too
    little area-specific signal to trust its area coefficient for that area.
    `model_confidence="none"` only happens on a still-empty platform, where
    not even a market average can be computed.
    """
    trained = train_price_model()
    return predict_price_from_model(trained, features)
