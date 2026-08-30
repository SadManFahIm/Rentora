# Phase 19.1 — Property Intelligence Score

> **This score is an informational property intelligence indicator. It is not
> a property valuation, fraud verdict, or guarantee of rental performance.**

Phase 19.0 (Agent SDK) is complete. This phase upgrades the existing
transparent Listing Quality engine into a composite, explainable
**Property Intelligence Score (0–100)** that combines six existing Rentora
signals. Nothing new is invented: every category is a deterministic,
rule-based composition of data the platform already stores.

---

## 1. Design goals & non-goals

**Transparent** — every point is attributed to a named component with a
weight and a contribution; the API returns the full breakdown, never one
opaque number.

**Deterministic** — identical inputs always produce the identical score
(no LLM, no randomness). Score version `property_intelligence_v1` is part of
every output and every cache key, so semantics are reproducible.

**Configurable** — component weights, levels, cache TTL and the engine
master switch live in Django settings, exactly like the existing
`LISTING_QUALITY_*` settings.

**Cached** — the composite is cached through the existing hardening helpers
(`config/cache_utils.py`) under a key that includes room ID, score version
and a *config signature*; important source changes invalidate the entry.

**Auditable** — reproducible + versioned + staff provenance view. Because
the score is a pure function of live data, any historical value can be
recomputed byte-identical.

**Not** a valuation, **not** a fraud verdict, **not** a demand guarantee —
stated in the API, in docs and in the agent tool description.

---

## 2. Architecture — what already exists and what this phase adds

Audit conclusion: **every source signal already exists**. The platform has
no persisted commute data, no PostGIS and no persisted score — so the design
(a) never fabricates travel times, (b) marks signals `unavailable` instead
of guessing, and (c) adds **no new database tables**.

| # | Component | Existing source (reused) |
|---|-----------|---------------------------|
| A | `listing_quality` | `rooms/listing_quality.get_listing_quality(room, market_stats)` — 0–100, 6 explainable categories, weight settings `LISTING_QUALITY_WEIGHTS`, level ladder `LISTING_QUALITY_LEVELS`. |
| B | `price_value` | `pricing.services.insight.get_price_insight(room)` — compares `room.price` vs the `MarketStat` snapshot for `(area, room_type)`; `None` when segment sample < 3. |
| C | `location` | `rooms.map_intel.metro_access_score(lat, lng)` — 0–100 MRT walk score over the curated `METRO_STATIONS` set; `None` when lat/lng are absent. |
| D | `photo_trust` | `RoomImage` (count, primary, `photo_gps_accuracy`), `PhotoModeration.risk_score`, Phase 17 `FraudSignal` detectors `duplicate_image` / `manipulated_image` / `photo_geo_mismatch`. |
| E | `trust` | `Room.verified`, owner `nid_verified` / `tenant_verified` (Phase 17 KYC), `FraudReport.severity`. |
| F | `demand` | `RoomView` + `Wishlist` + `Booking` 30-day counts per room, `rooms.map_intel._area_demand(area)` weighted index, `analytics.forecast.area_demand(area)` macroscopic index. |

New artifacts (all in a new `property_intelligence` app):

- `scoring.py` — pure, DB-free scoring functions (components, weight
  redistribution, confidence, suggestions, strengths, version/signature).
- `engine.py` — one-time data fetch + composition + cache orchestration
  (`get_property_intelligence(room, *, include_internal=False)`).
- `views.py` / `urls.py` — public + staff endpoints.
- `signals.py` — cache invalidation for material changes.
- `agent_tool.py` — READ_ONLY Agent SDK tool `property.intelligence`.
- `tests.py` — full coverage. No migrations (no new tables).

Integration points touched: `rooms/serializers.py` (new backward-compatible
field), `agents/tools.py` (registry hook), `config/settings/base.py`
(settings block), `config/urls.py` (route), `INSTALLED_APPS`.

---

## 3. Component definitions (0–100 each)

### A. `listing_quality` — reuse
Score and `level` come straight from the existing engine, which already
returns `{score (0–100), level, category_scores, suggestions}`. Availability:
`unavailable` only when `LISTING_QUALITY_SCORE_ENABLED` is off.

### B. `price_value` — price competitiveness (never a valuation)
Uses `get_price_insight`. Classification → 0–100:

| classification | `percentage_diff` | score |
|---|---|---|
| `great_deal` | < −15% | 95 |
| `good_price` | −15 … −5% | 90 |
| `fair_price` | −5 … +5% | 75 |
| `above_average` | +5 … +15% | 45 |
| `overpriced` | > +15% | 20 |

`unavailable` when `get_price_insight` returns `None` (no segment or
`sample_size < 3`) — we never fabricate a benchmark. The marketplace jargon
is **price competitiveness**, explicitly documented as not a valuation.

### C. `location` — metro / commute value
`metro_access_score(lat, lng)` (0–100). When lat/lng are missing → signal
`unavailable` with the explainable note *"Commute data is unavailable for
this listing."* No travel time is invented: this phase uses only walking
distance to curated MRT stations (dead-reckoning, labelled as such).

### D. `photo_trust` — completeness + authenticity (never a verdict)
Base = photo completeness mapped to 0–100 (reusing the quality engine's
photo rules: 0/50/75/100 for 0/1/2/4+ photos, capped 60 without a primary).
Then **authenticity deductions** only when a Phase 17 detector actually
fired:
`duplicate_image` −10/−20/−30 · `manipulated_image` −10/−20/−30 ·
`photo_geo_mismatch` −15 (by signal severity low/medium/high). A
`PhotoModeration.risk_score` ≥ 60 deducts −20. Positive authenticity: one
geotagged photo whose EXIF GPS is consistent with the room +8.
Deductions are phrased as *"photo authenticity signals reduced the trust
component by X points"*, never *"this listing is fraudulent"*.

### E. `trust` — verification & fraud signals (safe public explanation)
Base 55 (neutral). Add: `room.verified` +25 / −15 otherwise;
owner `nid_verified` +10; owner `tenant_verified` +5. If a `FraudReport`
exists: severity `clean` +5, `low` −10, `medium` −25, `high` −40. If no
report exists the component is treated as *partially* available (verification
flags only) with a note. Raw `FraudReport.score`, graph IDs and phone/NID
data are **never** exposed publicly — staff see severity + detector names
only.

### F. `demand` — booking strength (avoids small-sample bias)
Per-room 30-day engagement `views + saves*3 + booking_requests*6`
(matching the existing map-intel weight), normalised `min(100, raw/20*100)`.
Blend 40% own + 60% area (`_area_demand`), but:
- own signals == 0 **and** area total < 3 → `unavailable`
  (*"Not enough activity data yet."*);
- own < 2 → area-weighted only + note *"Listing has limited recent demand
  data."* (reduces confidence, never claims confidence it lacks).

Raw traffic and conversions are conflated nowhere — bookings/wishlists are
weighted above views.

---

## 4. Composite formula, weights & boundedness

Components are the six above. Settings:

```python
PROPERTY_INTELLIGENCE_WEIGHTS = {
    "listing_quality": 25,
    "price_value": 20,
    "location": 15,
    "photo_trust": 15,
    "trust": 15,
    "demand": 10,
}
```

- Weights are validated at compute time: numeric, non-negative, exactly
  summing 100. On mis-configuration the engine logs a warning and falls back
  to these documented defaults (mis-configuration must never 500 the API).
- The overall score is only defined over **available** components:
  `effective_weight = weight * (100 / sum(available weights))` redistributes
  the unavailable weight proportionally, so the score stays 0–100 and is
  still honest (missing signals never silently inflate the total).
- `contribution = effective_weight * score / 100`; `total = round(sum)`.
- If *no* component is available the score is `null` (never 0).

### Confidence (not another arbitrary score)
Deterministic rule: base = availability count (≥5 → 3, 3–4 → 2, <3 → 1),
−1 when demand unavailable, −1 when the listing is stale (`updated_at`
older than `PROPERTY_INTELLIGENCE_STALE_DAYS`, default 90), −1 when the
price benchmark sample is small (< 5). Map ≥3 → `high`, 2 → `medium`,
≤1 → `low`; `none` when the whole score is unavailable. `reasons` lists the
human-readable factors that drove the tier.

### Suggestions & strengths (deterministic, rule-based)
Suggestions come from the existing quality engine plus per-component rules
(price above market, few photos / no primary, incomplete verification,
limited demand, unavailable commute, stale data). Strengths list components
scoring ≥ 75. No LLM is used for any of this — hallucination impossible.

---

## 5. Cache, versioning, invalidation

- Key: `property-intelligence:{room_id}:{config_signature}` where
  `config_signature` = sha256 over `SCORE_VERSION` + weights + levels +
  thresholds + master switch. A configuration change therefore auto-fires a
  new key (configuration invalidation by construction).
- Enforced through `safe_cache_get/set` (degrade to compute, never crash).
- TTL `PROPERTY_INTELLIGENCE_CACHE_TTL_SECONDS` (default 900 s).
- Invalidation signals (`property_intelligence/signals.py`):
  - `Room` post-save (price, area, lat/lng, address, amenities,
    availability, verification, title/description) — delete the key.
  - `RoomImage` post-save / post-delete (count, primary, GPS).
  - owner `User` post-save when verifation fields actually change
    (pre-save stash pattern, capped at 100 listings per owner).
  - Demand/booking/view changes are **not** signalled (hot paths) — the
    short TTL self-refreshes demand; documented limitation, never stale
    forever.

---

## 6. API surface

All under `api/v1/property-intelligence/`, following existing Rentora
conventions (`{"detail": ...}` errors, DRF, `extend_schema`).

### `GET /api/v1/property-intelligence/<room_id>/` — public
Read access follows the platform default (`IsAuthenticatedOrReadOnly`,
same as room detail). Response:

```json
{
  "room_id": 5,
  "score": 82,
  "confidence": "medium",
  "score_version": "property_intelligence_v1",
  "computed_at": "…",
  "breakdown": {
    "listing_quality": {"score": 88, "weight": 25, "effective_weight": 27.8,
                        "contribution": 24.4, "level": "good", "availability": "available"},
    "price_value": {"score": 79, "weight": 20, "effective_weight": 22.2,
                    "contribution": 17.6, "availability": "available", "note": "…"}
  },
  "strengths": ["Complete, market-ready listing."],
  "suggestions": ["Price is above comparable listings in this area."],
  "data_freshness": {"room": "…", "market": "…|null", "fraud": "…|null",
                     "photos": "…|null", "demand": "…"},
  "disclaimer": "This score is an informational property intelligence indicator. It is not a property valuation, fraud verdict, or guarantee of rental performance."
}
```

**Never exposed publicly:** `FraudReport.score`, graph/ring IDs, detector
details beyond the generic photo-trust note, NID/phone/device data, price
prediction internals, telemetry.

### `GET /api/v1/property-intelligence/<room_id>/staff/` — staff/admin
Gate: `request.user.is_staff or role == "admin"` (same convention as
`rooms/insights`, returns 403 `{"detail": "Admin access required."}`).
Adds `provenance` (market benchmark: avg/median/percentiles/sample_size/
calculated_at; fraud: report_exists/severity/status/detector names but no
raw evidence; verification booleans; photo detail; demand counts) and
`engine` (version, config signature, weights, cache hit). Staff access is
audit-logged. Staff still never see raw sensitive data.

---

## 7. Serializer integration (backward compatible)

`RoomDetailSerializer.listing_quality` is untouched. A new nullable
`property_intelligence_score` field returns a light payload
`{score, confidence, score_version, computed_at, disclaimer}` (no breakdown —
full detail lives at the dedicated endpoint). Enabled by
`PROPERTY_INTELLIGENCE_SERIALIZER_ENABLED` (default True). The detail
serializer renders one room, and scores are Redis-cached, so there is no
N+1 and no per-row recomputation; the list serializer is unchanged.

---

## 8. Agent tool — `property.intelligence`

Registered through the Phase 19.0 `AgentToolRegistry` via the SDK's single
registration path (`register_builtin_tools`). Spec: READ_ONLY, JSON schema
`{"room_id": integer ≥ 1, "include_breakdown": false}`. Executor resolves
the room, computes via the same engine and returns the **public** payload
(breakdown optional). Enforced: server-side READ_ONLY executes immediately,
is schema-verified, persisted as an audited `AgentToolCall` with duration +
telemetry through the run, and cannot modify the score or listing. The tool
description and output explicitly forbid the agent labelling the score as a
valuation or fraud verdict — the tool is authoritative and grounded.

---

## 9. Security / privacy

- RBAC: public read only; staff endpoint gated; agent tool READ_ONLY.
- Redaction: public/staff payloads never include NID, phone, device,
  graph/ring IDs, raw `FraudReport.score`, or provider/model internals.
- Tenant isolation: only room-derived aggregates; owner identity surfaced
  only via existing public `RoomOwnerSerializer` fields.
- Audit: staff endpoint access logged via `fraud.services.privacy.audit_log_access`;
  agent tool calls audited by the SDK.

## 10. Performance

One compute does ~8 small indexed queries (room+owner, images, market stat,
fraud report+signals, 30-day own counts ×3, area demand ×3) — amortised by
the 15-minute Redis cache, single-room fetch, no LLM, no repeated scans.

## 11. Testing matrix

Scoring (bounds, weighting, determinism, missing/low data, confidence,
version) · Price (comparable, insufficient, price change→invalidation) ·
Location (present / missing) · Photos/Trust (signals, missing, public
redaction) · Demand (sufficient / insufficient / stale) · Cache (hit, miss,
invalidation, config change) · API (valid/404, auth, public safety, staff
RBAC) · Agent tool (registration, schema, auth, telemetry, read-only) ·
Regression (listing_quality byte-compatible).

## 12. Limitations / honest unavailability

- No commutes beyond metro walking distance (no persisted routing); OSRM is
  off by default and never relied on.
- Demand is a lower bound (anonymous viewers aren't tracked) and is
  `unavailable` until a minimum signal exists.
- Price-vs-market only when a ≥3-sample segment snapshot exists.
- The score is deterministic, versioned and cached — not a model, not a
  forecast, not a guarantee.