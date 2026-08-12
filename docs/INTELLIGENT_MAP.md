# 🗺️ Rentora Intelligent Rental Decision Map

> **Phase 7 v2** — the map evolved from a property map into a **Rental Decision
> Intelligence Platform**: it answers *"given my budget, destination and
> preferences, where is the best place for me to live?"* instead of just
> showing pins.

Built as an extension of the existing **MapLibre GL JS** map (Phase 7) on top
of Rentora's existing search, pricing, fraud, listing and location systems.
**No existing Phase 7 behaviour was rewritten.**

---

## What was already there (Phase 7)

- Dhaka map on OpenStreetMap tiles, dark/light themes, key-free
- Price markers, marker clustering, radius search
- Travel-time isochrone overlay, street search + autocomplete, Dhaka gazetteer
  with Nominatim fallback
- Directions + ETA, walking/driving/transit, Google Maps deep-link
- Metro ETA, area count chips, MRT Line-6 polyline, price heatmap
- Map + list split view, shareable map URLs, viewport/bbox caching
- Room-count API badge, landlord listing location picker

## What v2 adds

| Feature | What it does |
|---|---|
| **AI Smart Map Search** | Bangla / English / Banglish free-text → structured filters → map flies to the result area, pins update, chips show the applied intent |
| **Metro Commute Score** | 0-100 transit-access score per listing (walking time to the nearest MRT station) |
| **Commute mode** | Pick a destination (office / university / any point) — every visible listing gets a walking-time estimate; filter by max commute |
| **Best Value Score** | 0-100 transparent blend of price-fit, amenities, listing quality, verification, demand and metro access (server-side, explainable factors) |
| **Area Intelligence panel** | Avg/median rent, listings, availability, demand (views/saves/bookings), price trend, metro access per area — real data only |
| **Area comparison** | Select up to 3 areas → side-by-side table |
| **Affordability map** | Your budget → % of currently listed rooms per area that fit (real listing shares, not estimates) |
| **Ideal Area ranking** | Budget + optional destination → ranked areas with *why* (budget fit, commute, availability, metro) |
| **Value-score pins** | Marker popups show ⭐ value score + transit factor alongside price |

## Architecture

```text
              User query / budget / destination
                          │
              ┌───────────▼───────────┐
              │  rooms/map_intel.py   │   engine (pure, testable)
              └───────────┬───────────┘
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
  parse_map_query    commute_eta      value_score
  (reuses nl_query)  (haversine +     (weighted blend,
                     MRT corridor)     cached 15 min)
        │                 │                  │
        └─────────┬───────┴───────┬──────────┘
                  ▼               ▼
          map_search_rooms   affordability_stats
                  │           ideal_areas
                  ▼
        RoomViewSet actions  /api/v1/rooms/map-intel/*
                  │
                  ▼
        MapIntelPanel (React) + existing map
```

### Principles

- **Reuse, don't duplicate** — `parse_nl_query`, the room queryset, pricing
  `MarketStat`, the listing-quality engine, curated metro stations, the
  gazetteer's area centres and the existing bbox cache are all reused.
- **No hallucinated data** — every price, percentage, ETA, demand score and
  recommendation is computed from rows already in the database; areas with no
  data report `null`/`—`, never invented numbers.
- **Honest estimates** — walking/driving ETAs are straight-line heuristics
  explicitly labelled `estimate: true`. Transit ETA is only produced when both
  endpoints sit within 1.2 km of an MRT Line-6 station; otherwise the API
  honestly says transit routing is unavailable.
- **Privacy** — no private owner coordinates beyond the listing coordinate, no
  per-user history, no internal fraud scores. Demand is aggregate 30-day
  counts only.

## Feature flags

All in `backend/config/settings/base.py` (defaults shown):

| Setting | Default | Meaning |
|---|---|---|
| `MAP_WALKING_SPEED_KMH` | `4.8` | walking heuristic speed |
| `MAP_DRIVING_SPEED_KMH` | `24.0` | driving heuristic speed |
| `MAP_METRO_BOARDING_KM` | `1.2` | max distance to board the MRT corridor for transit ETA |
| `MAP_METRO_TRAIN_SPEED_KMH` | `33.0` | corridor average speed |
| `MAP_VALUE_PRICE_WEIGHT` … `MAP_VALUE_METRO_WEIGHT` | 0.30/0.20/0.15/0.10/0.10/0.15 | value-score weights |

## Performance

- Value scores are cached 15 minutes per room (invalidated by `updated_at`).
- Area stats / affordability are cached client-side via React Query
  (`staleTime` 1–10 min) and run as aggregate SQL (no N+1 fetches of full
  rows — only `lat/lng` is pulled for metro scoring, capped at 200 rooms).
- NL search caps candidates at 200 rooms, amenities intersect in Python (the
  JSON `contains` lookup is Postgres-only; SQLite can't express it).
- No AI model is called per viewport move — all endpoints are deterministic
  SQL/heuristics.

## Limitations

- Routing is straight-line based; no road-network walking/driving ETA yet
  (needs an optional routing provider, e.g. OSRM).
- Transit ETA exists only along the MRT Line-6 corridor and only when both
  ends are near a station.
- Area centres come from the existing gazetteer (`streets.py`); areas absent
  from the gazetteer report `null` centres.

See also:

- [MAP_API.md](./MAP_API.md) — endpoint reference
- [MAP_SCORING.md](./MAP_SCORING.md) — scoring formulas
- `backend/rooms/map_intel.py` — the engine
- `frontend/src/components/MapIntelPanel/MapIntelPanel.tsx` — the panel UI
