# 🤖 Rentora Copilot

Conversational room discovery — ask for a place in natural Bangla or English and
Copilot searches the **live** listing database.

```text
User message
     ↓
Intent extraction (reuse rooms.nl_query + amenity/property words)
     ↓
Existing search pipeline (hard filters → hybrid semantic ranking)
     ↓
Rule-based response generator over *retrieved* rows only
```

## Architecture

Hybrid by design — **no LLM is required and none is called**:

1. **Intent extraction** — reuses the Phase-11 natural-language parser
   (`rooms/nl_query.py`) for budget / area / room type / gender / move-in month,
   plus an amenity + property-type word table (Bangla + English + Banglish:
   WiFi, AC, Furnished, Parking, Attached Bath, Kitchen, Pet Friendly…).
2. **Retrieval** — the same pipeline as smart search: hard filters always gate
   first (a ৳10,000 budget can never be "discovered" past), then the hybrid
   ranking (`rooms/ranking.py`) — neural + lexical relevance, personalization,
   listing quality, fraud-aware demotion.
3. **Response** — a deterministic generator that only ever asserts what the
   retrieved rows contain: listing titles, prices, areas, amenities. It cannot
   hallucinate a room, price or availability, because it has no generative step.

### Conversation context

Follow-up messages keep their constraints: the client echoes a `session_id`
and the server stores the accumulated structured filters in the Django cache
(1h TTL). "শুধু furnished দেখাও" after an Uttara/৳10,000 query keeps Uttara +
budget and adds `Furnished`. `reset` / `clear` / নতুন করে starts fresh.

## API

`POST /api/v1/copilot/chat/` — public (like the rooms list), throttled
(`copilot` scope, 60/hour).

```json
{
  "message": "Uttara-তে ১০ হাজারের মধ্যে furnished student room চাই"
}
```

```json
{
  "session_id": "abc…",
  "message": "I found 2 matching rooms in Uttara · under ৳10,000.\n\n1. Budget Student Room, Uttara Sector 10 — Uttara — ৳8,500/mo (Single)\n   ✓ WiFi, Furnished, Attached Bath",
  "intent": { "budget_max": 10000, "areas": ["Uttara"], "amenities": ["Furnished"], "hints": ["Budget ≤ ৳10,000", "Uttara", "Furnished"], "…": "…" },
  "listings": [ { "id": 29, "title": "…", "price": 8500, "area": "Uttara", "room_type": "single", "amenities": ["WiFi", "Furnished"], "verified": true, "tier": "free", "image": null } ],
  "total_count": 2,
  "suggestions": ["দাম অনুযায়ী সাজাও"]
}
```

### Privacy

Only public listing fields are returned — no owner contact details, no fraud
scores, no internal data. Sessions hold the user's own filters only.

## Configuration

| Env / setting | Default | Meaning |
| --- | --- | --- |
| `COPILOT_ENABLED` | `True` | Master switch (503 when off) |
| `COPILOT_MAX_RESULTS` | `5` | Listings per turn |
| `COPILOT_SESSION_TTL_SECONDS` | `3600` | Follow-up context lifetime |
| throttle scope `copilot` | `60/hour` | Bound on search-engine usage |

## UI

A floating bottom-right button (hidden on `/auth`) opens a chat panel —
mobile responsive, accessible, consistent with the app theme. Listing cards
carry a **View** action that opens the full RoomModal, quick-reply chips
(backend-generated suggestions), and "AI understood" intent pills.

## Failure behavior

- No results → honest "couldn't find a match" + suggestions to relax filters.
- Ranking signals unavailable → falls back to default listing order.
- Disabled flag → 503. Empty message → 400. All degrade, never crash.
- Greetings/reset are handled without a search round-trip.

## Tests

`copilot/tests.py` — intent extraction (Bangla/English/mixed), follow-up
context preservation, hard-filter integrity, hallucination guard (every
listing in a reply exists in the DB and obeys the budget/area), no-result
handling, greetings/reset, API contract, disabled flag.

## Limitations

- Amenities are matched by substring against the listing's `amenities` JSON —
  spelling variants outside the word table fall through to semantic relevance.
- No multi-turn "compare these two" memory beyond the structured filters.
- An optional LLM summarizer is a deliberate future extension point; if added
  it will only re-phrase retrieved rows, never invent.
