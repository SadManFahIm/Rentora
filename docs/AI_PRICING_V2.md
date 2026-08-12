# 🏷️ AI Landlord Pricing Suggestion v2

Demand-aware, market-aware pricing intelligence on top of the existing
fair-price prediction engine (`pricing/services/prediction.py`).

## What it answers

```text
Recommended price: ৳12,500     Range: ৳10,000 – ৳15,000
Demand: Moderate (41/100)      Confidence: 78%
Time-to-rent: 8–15 days        (or "Insufficient historical data")
Why? • Similar Uttara singles average ৳10,200
     • Your price is 14% above comparable listings
     • Current demand is high (142 views · 3 booking requests in 30 days)
```

## Architecture

`pricing/services/suggestion.py` composes four signals — **all from real
data, nothing trained a second way**:

1. **Price range** — the existing Ridge regression
   (`predict_price_from_model`), reused verbatim; the recommended price is
   the model's prediction rounded to the nearest ৳500 (no meaningless
   precision like ৳10,037.42).
2. **Demand score (0–100)** — `30` base + room views vs area peers + wishlist
   saves + booking requests + area heat vs platform average. Raw page views
   alone are never treated as demand; the raw counts are returned so the UI
   can show the landlord what went in.
3. **Time-to-rent** — median-of-actual-history: for every approved booking in
   the same area, days between *that listing's* creation and the booking
   (P25–P75 range). Fewer than 5 samples → `available: false` +
   "Insufficient historical data" — never a fabricated number.
4. **Confidence** — composite: model confidence (high/low/none) + market
   sample presence + demand-signal availability, clamped 0..1.

**Explainability** — every `reason` is a calculated fact the landlord can
verify ("Similar Mirpur singles average ৳8,500", "Model trained on 33 current
listings").

**Caching** — results are cached (locmem dev / Redis prod) keyed by room id +
room `updated_at` + price + market snapshot `calculated_at`, so the endpoint
isn't recomputed on every page load and a price/market change invalidates
immediately.

## API

`GET /api/v1/pricing/suggestion/<room_id>/` — **owner or admin only** (a
pricing recommendation is the landlord's business data, not public).

Response (abridged):

```json
{
  "room_id": 12,
  "current_price": 8000.0,
  "min_price": 10000,
  "recommended_price": 12500,
  "max_price": 15000,
  "confidence": 0.78,
  "model_confidence": "low",
  "demand_score": 41.2,
  "demand_label": "Moderate",
  "time_to_rent": { "available": true, "days_min": 8, "days_max": 15, "sample_count": 9 },
  "reasons": ["Similar Mirpur single listings average ৳8,500", "…"],
  "signals": { "room_views_30d": 142, "wishlist_count": 2, "booking_requests": 3, "…": "…" },
  "market_avg_price": 8500.0
}
```

## UI

Dashboard → **Insights** → each listing row has an **AI Price** toggle that
expands a suggestion card: range, demand label, confidence, time-to-rent,
reasons, and a **Use ৳12,500** button.

**The landlord always decides.** The "Use" button just PATCHes the room price
through the normal update endpoint — nothing changes prices automatically.

## Configuration

| Env / setting | Default | Meaning |
| --- | --- | --- |
| `PRICE_ROUND` (module) | 500 | BDT rounding granularity |
| `MIN_TIME_TO_RENT_SAMPLES` (module) | 5 | History floor before claiming a range |
| `CACHE_TIMEOUT` (module) | 3600s | Stale-but-unchanged cache bound |

## Tests

`pricing/test_suggestion.py` — suggestion shape + ৳500 rounding, range
contains recommendation, demand score bounds + rises with engagement, demand
band labels, insufficient-data handling, time-to-rent with history, reasons
are calculated, cache hit/miss + price-change invalidation, and the
owner/admin/other/anonymous permission matrix.

## Limitations

- The Ridge model is trained on the current catalogue; brand-new areas with
  few listings fall back to the overall market average (flagged `low`/`none`
  confidence) — honest, never a confident-looking guess.
- Time-to-rent is an estimate, never a guarantee, and depends on booking
  history accumulating.
