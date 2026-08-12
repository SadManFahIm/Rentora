# 🗺️ Intelligent Map — API Reference

All endpoints are **public GET** actions on the room viewset
(`/api/v1/rooms/map-intel/*`), follow the existing API conventions and return
JSON. No authentication required (same as the room list).

## `GET /api/v1/rooms/map-intel/stats/`

Per-area aggregate statistics. Query param: `?area=Uttara` to narrow to one
area (omit for all areas, ordered by listing count).

```json
[
  {
    "area": "Uttara",
    "lat": 23.8759,
    "lng": 90.3795,
    "listings": 248,
    "available": 210,
    "avg_rent": 11200.0,
    "median_rent": 10500.0,
    "min_rent": 6000.0,
    "max_rent": 25000.0,
    "avg_size_sqft": 850,
    "demand": {
      "score": 80,
      "label": "Very High",
      "views_30d": 1200,
      "saves_30d": 96,
      "bookings_30d": 14,
      "listings": 248
    },
    "metro_access": 95,
    "price_trend_pct": 8.2
  }
]
```

- `metro_access` — 0-100, mean walking-time score of the area's listings.
- `price_trend_pct` — % change between the latest `MarketStat` average and the
  live listing average; `null` when no market snapshot exists.

## `GET /api/v1/rooms/map-intel/commute/`

ETA between two coordinates. Params: `from_lat`, `from_lng`, `to_lat`,
`to_lng` (all required numbers), `mode` ∈ `walking | driving | transit`
(default `walking`). 400 on missing/invalid params or mode.

```json
{
  "mode": "transit",
  "minutes": 41,
  "distance_km": 11.8,
  "estimate": true,
  "detail": "MRT Line-6 estimate: 9 min walking + 32 min ride"
}
```

- `estimate: true` → minutes are a heuristic (straight-line, or MRT corridor).
- `estimate: false` + `minutes: null` → transit routing genuinely unavailable
  for this pair (neither end is within 1.2 km of an MRT station).

## `GET /api/v1/rooms/map-intel/value/`

Per-room value scores. Params: `ids=1,2,3` (comma list). Response keyed by
room id:

```json
{
  "1": {
    "score": 91,
    "factors": {
      "price_fit": 100,
      "amenities": 28,
      "quality": 47,
      "verified": 100,
      "demand": 80,
      "metro": 95
    },
    "price_vs_market_pct": -5.0
  }
}
```

## `GET /api/v1/rooms/map-intel/affordability/`

% of currently listed rooms per area within a budget. Params: `budget`
(positive number, required; 400 otherwise).

```json
[
  { "area": "Mirpur", "lat": 23.8069, "lng": 90.3687, "total": 421, "within_budget": 400, "percent": 95 }
]
```

## `GET /api/v1/rooms/map-intel/ideal-areas/`

Ranked areas for a user profile. Params: `budget` (required), optional
`work_lat`, `work_lng`, `max_commute` (default 45), `room_type`. Returns the
top 6 areas with reasons:

```json
[
  {
    "area": "Mirpur",
    "lat": 23.8069,
    "lng": 90.3687,
    "score": 88,
    "avg_rent": 9000.0,
    "affordability_pct": 100,
    "commute_minutes": 28,
    "metro_access": 82,
    "listings": 421,
    "reasons": [
      "100% of Mirpur listings fit your ৳10,000 budget",
      "~28 min commute to your destination (MRT estimate)"
    ]
  }
]
```

## `GET /api/v1/rooms/map-intel/search/`

Natural-language map search. Params: `q` (free text, Bangla / English /
Banglish). Empty `q` → empty safe result. Returns the parsed intent, matching
rooms (up to 20 serialized) and a fly-to target:

```json
{
  "query": "উত্তরায় ১২ হাজারের মধ্যে furnished room",
  "intent": {
    "budget_max": 12000,
    "areas": ["Uttara"],
    "room_type": null,
    "gender": null,
    "months": [],
    "hints": ["Budget ≤ ৳12,000", "Uttara", "Furnished"],
    "amenities": ["Furnished"],
    "metro_walk": false,
    "raw": "উত্তরায় ১২ হাজারের মধ্যে furnished room"
  },
  "count": 1,
  "rooms": [ { "id": 29, "title": "Student Room, Uttara Sector 10", "price": 8500, "area": "Uttara" } ],
  "target": { "lat": 23.8759, "lng": 90.3795, "kind": "area", "name": "Uttara" }
}
```

- `target.kind` is `"area"` (gazetteer centre) or `"metro"` (nearest MRT
  station) when the query asks for metro proximity.
- Filters are **hard filters on real data** — the map never invents listings.

### Query understanding

- Budgets: `12k`, `12,000`, `১০ হাজার`, `under 15k`, `এর মধ্যে`
- Areas: canonical + Bangla/Banglish aliases via the existing gazetteer
- Amenities: `furnished`, `wifi`, `ac`, `attached bath`, `parking`, `gym`,
  `kitchen`, `pet friendly` (word-boundary matched — `kache` can't match `ac`)
- Metro: `metro`, `মেট্রো`, `mrt`, `station`, `স্টেশন`
- Room types: `single`, `shared`, `studio`; gender: male/female
