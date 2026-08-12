# 🧮 Intelligent Map — Scoring Reference

Every score below is **deterministic, configurable and computed server-side**
from real platform data. Weights live in `backend/config/settings/base.py`.

---

## Metro Access Score (0-100)

Walking minutes to the nearest curated MRT station:

```text
minutes = (haversine_km(listing, station) / MAP_WALKING_SPEED_KMH) * 60
score   = clamp(100 - (minutes / 30) * 100, 0, 100)
```

| Walking time | Score |
|---|---|
| ≤ 5 min | 100 |
| 15 min (≈1.2 km) | 50 |
| 30 min | 0 |

Area `metro_access` is the **mean** of the area's listings' scores.

---

## Commute ETA

| Mode | Formula | Labelled |
|---|---|---|
| walking | `haversine_km / 4.8 km/h` | `estimate: true` |
| driving | `haversine_km / 24 km/h` | `estimate: true` |
| transit | corridor interpolation only when **both** ends ≤ 1.2 km from an MRT station: `walk(a+b) + ride(haversine(stations) / 33 km/h)` | `estimate: true` |
| transit (no corridor) | `minutes: null` + honest explanation | `estimate: false` |

ETAs are **straight-line heuristics**, never turn-by-turn routes — the API
always labels them.

---

## Value Score (0-100)

Transparent weighted blend of six explainable factors:

```text
score = price_fit×0.30 + amenities×0.20 + quality×0.15
      + verified×0.10 + demand×0.10 + metro×0.15
```

| Factor | Definition |
|---|---|
| **price_fit** | `clamp(100 − (price / median_price − 1) × 150, 0, 100)` vs the area+type `MarketStat` median; 60 when no market baseline exists |
| **amenities** | `min(100, count × 14)` (10 supported slots) |
| **quality** | existing listing-quality engine score (0-100) |
| **verified** | `100` if KYC-verified, else `0` |
| **demand** | 30-day area demand score + `own_views × 2`, capped at 100 |
| **metro** | Metro Access Score above |

`price_vs_market_pct` reports `(price/median − 1) × 100` — a negative value
means the listing sits *below* its market median.

Cached 15 minutes per room, keyed on `updated_at` so edits invalidate it.

---

## Demand Score (per area, 0-100)

Weighted 30-day engagement per listing — a save is worth more than a view, a
booking request more than a save:

```text
raw   = (views + saves×3 + bookings×6) / listings
score = min(100, (raw / 20) × 100)
```

| Score | Label |
|---|---|
| ≥ 81 | Very High |
| 61–80 | High |
| 31–60 | Moderate |
| ≤ 30 | Low |

---

## Affordability (per area)

Not a score — the **real share** of currently listed rooms in the area within
the user's budget:

```text
percent = round(100 × rooms(area, price ≤ budget) / rooms(area))
```

---

## Ideal Area Ranking (0-100)

```text
score = affordability×0.40 + commute×0.30 + availability×0.15 + metro×0.15
```

| Component | Definition |
|---|---|
| **affordability** | `min(100, percent × 1.2)` from the affordability table |
| **commute** | `clamp(100 − (commute_minutes / max_commute) × 100, 0, 100)`; defaults to 75 when no destination is set or no area centre exists |
| **availability** | `100 × available / listings` |
| **metro** | area mean metro-access score |

Areas with zero listings are skipped; every recommendation carries `reasons`
quoting the exact numbers used (budget %, commute minutes, listing counts).
