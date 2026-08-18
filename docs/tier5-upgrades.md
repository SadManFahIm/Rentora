# Tier-5 Upgrades — Funnel Analytics, Photo Forensics v2, Price Advisor, Copilot Vision, AI Drafts

**Shipped:** roadmap 12.10 · Phase 12 follow-up batch

Tier-5 closes the remaining *product* gaps from the Tier-1–4 batches: the
conversion funnel is now fully wired end-to-end, the photo-moderation
pipeline detects real watermark styles it couldn't before, the demand
forecast is linked to individual listings, and the Copilot/listing form
understand and draft from the actual listing content.

Everything stays deterministic, self-hosted and honest — no paid APIs, no
LLM calls, no invented claims.

---

## 1. Conversion funnel fully wired

The self-hosted analytics funnel previously stopped at `booking_requested`:
`booking_confirmed` and `payment_completed` were defined but never emitted,
so the funnel under-reported real conversion (documented in tier2).

**Now:**

- `booking_confirmed` — recorded **server-side** in the booking approval
  signal (`bookings/signals.py`) with `room_id`/`booking_id`, attributed to
  the tenant.
- `payment_completed` — recorded **server-side** on the payment SUCCESS
  transition (`payments/views.py::_apply_success_side_effects`) with
  `payment_type`/`amount`/`booking_id`/`room_id`.
- `room_view` — fired client-side when a listing modal opens (RoomModal).
- `chat_started` — fired client-side when a conversation is selected
  (ChatWindow).

The full funnel `page_view → room_view → chat_started → booking_requested →
booking_confirmed → payment_completed` now counts distinct authenticated
users per step. Server-side recording means a forged or lost client can't
break the last two steps. No PII ever enters event properties (same bounded
payload contract as the capture endpoint).

New helper: `analytics.services.record_event(user, event, category,
properties, path)`.

## 2. Photo forensics v2 — watermark & text overlays

Extends `fraud/services/image_forensics.py` (ELA + uniform-band watermark
from Tier 2) with two deterministic heuristics:

- **Text-overlay detection** (`text_overlay`) — caption / phone-number
  watermarks are *dark strokes on a bright photo*. A tile containing
  lettering has both a meaningful share of very-dark pixels and a large
  share of bright pixels — a combination natural texture almost never
  produces. Thresholds tuned against the existing clean-photo suite.
- **Repeated-pattern detection** (`repeated_pattern`) — tiled/diagonal
  watermarks repeat the same small mark across the photo. We take the
  top-left corner tile (which must be *distinctive* — not flat, not noise)
  and count how many non-overlapping tiles match it. Real photos have no
  repeats; tiled watermarks have many.

Both surface as medium-severity `ForensicSignal`s in the fraud scan → the
existing admin photo-moderation queue. Honesty contract unchanged: every
signal is a suspicion to review, never proof.

## 3. Per-listing price recommendation

New `rooms/price_recommendation.py` + `GET /api/v1/rooms/<id>/price-recommendation/`
(owner/admin only — 403 for anyone else).

Combines three real signal sources into one grounded verdict:

1. **Area demand** — `analytics.forecast.area_demand` (index 0-100 +
   direction, from anonymized booking/wishlist/view counts).
2. **Market position** — `pricing.services.insight.get_price_insight`
   (below/at/above the segment average).
3. **Own interest velocity** — the listing's own booking requests +
   wishlist saves in the last 30 days.

Output: `direction` (raise/hold/lower), a `suggested_price` (capped at
±8% per suggestion, rounded to ৳100), `confidence` (high/medium/low from
how many signals are live), plain-language `reasons`, and an honest note
that it's a review aid, never an automatic price change. Thin data yields a
low-confidence hold — the engine never fabricates a number.

UI: a **Price recommendation** card on each row of the landlord's
Dashboard → Listings tab (`PriceRecommendationCard`).

## 4. Copilot image understanding

New `copilot/image_profile.py` + a `photos` aspect in the listing-mode
Copilot (`copilot/listing_qa.py`). Ask "দেখতে কেমন? / what does it look
like? / ছবি দেখাও" and the answer is built from the listing's **actual**
photos via deterministic pixel statistics:

- brightness (dark / normal / bright)
- colourfulness (muted / colourful)
- dominant tones (warm beige, cool grey, …) from quantized hue buckets

The answer explicitly says it's a statistical description of light and
colour — it never claims furniture, state or condition. Listings with no
photos get an honest "doesn't have any photos yet."

## 5. AI listing draft

New `rooms/description_generator.py` + `POST /api/v1/rooms/generate-description/`
(authenticated).

Landlords click **✨ AI draft** in the listing form (RoomForm) and get a
title + description + amenity tags drafted deterministically from the
fields they've already filled (area, type, price, size, gender, amenities).
Safe defaults when fields are empty; the note reminds the landlord to
review and edit before publishing. No LLM, nothing hallucinated, nothing
auto-published.

---

## Tests

16 new backend tests + 2 new frontend tests:

| File | Covers |
| --- | --- |
| `analytics/test_funnel.py` | `record_event` attribution, booking-approval → `booking_confirmed` (tenant-attributed), pending → no event |
| `rooms/test_price_recommendation.py` | grounded payload, thin-data honesty, rising-demand → raise, above-market → lower, endpoint owner/admin-only |
| `copilot/test_image_profile.py` | image profile stats, missing-file grace, photos aspect grounded + no-photo honesty, description draft grounded/no-invented-amenities, endpoint auth |
| `frontend/src/services/tier5Service.test.ts` | price-recommendation + generate-description API calls |

Full suites: **667 backend + 322 frontend (989 total)** — all passing.

## Screenshots

`docs/screenshots/tier5-price-recommendation.png` ·
`tier5-ai-draft.png` · `tier5-copilot-photos.png`
(capture script: `frontend/scripts/capture_tier5_shots.mjs` — backend :8000,
frontend :3001).

## Known limitations

- Text-overlay and repeated-pattern heuristics are tuned heuristics — the
  thresholds are sane defaults, not trained against a large real-world
  watermark corpus (same caveat as Tier-2 ELA).
- Price recommendation's `confidence` is a transparent signal-count, not a
  learned probability.
- Copilot image answers are statistical (light/colour), not semantic
  recognition — by design, and stated in the answer text.
- Funnel `payment_completed` only fires for payments that complete through
  the real gateway callbacks (SSLCommerz/bKash) — which is exactly when a
  payment is genuinely completed.
