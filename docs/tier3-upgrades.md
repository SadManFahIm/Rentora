# Tier-3 Upgrades — RAG Copilot, i18n, embeddings, E2E, trust signals

Rentora's third upgrade batch (merged as **12.8**). Every feature follows
the same rules as earlier phases: reuse the existing architecture, ship
behind safe toggles, degrade gracefully, and never break search.

---

## 1. RAG Copilot — listing-grounded Q&A

The Copilot was search-only. Tier 3 adds **listing mode**: the user asks
about one specific listing and the answer is generated strictly over that
listing's database row — the retrieval step *is* the listing.

### API

- `POST /api/v1/copilot/chat/` — accepts an optional `listing_id`. When
  set, the turn is grounded on that listing (mode `"listing"` in the
  response, plus a `listing` fact card and the answered `aspect`).
- `GET /api/v1/copilot/listing/<id>/` — the public, grounded fact card
  (title, price, area, type, gender, size, amenities, verified, address,
  description, nearest-metro km, image). 404 for missing/unavailable.

### How grounding works (`copilot/listing_qa.py`)

- Bilingual keyword sets (EN + BN + Banglish) map a question to an
  *aspect*: price, area, amenities, room type, gender, size, verification,
  availability, description.
- Each aspect's answer is built **only from real Room fields**. Unknown or
  unanswerable questions ("what's the landlord's phone?") are refused
  explicitly.
- No aspect detected → a factual summary of the listing (the classic
  "summarize the retrieved document" RAG behaviour).
- No LLM is called anywhere — no hallucination by construction.

### Frontend

- Room modal: **Ask Copilot about this listing** button opens the floating
  widget pre-seeded with a listing-grounded greeting.
- `stores/copilotStore.ts` is the cross-component channel; the widget
  subscribes and seeds the conversation, and every follow-up turn re-sends
  the `listing_id`.

## 2. Full EN ⇄ বাংলা UI toggle

`react-i18next` + `i18next` with inline dictionaries
(`src/i18n/en.json`, `src/i18n/bn.json`).

- **Navbar toggle** (`LanguageToggle` component) — switches instantly and
  persists to `localStorage` (`rentora_language`).
- **No flash of wrong language** — the stored language is read before the
  first render (`getStoredLanguage()`), `document.documentElement.lang` is
  set for accessibility, and tests load the dictionaries in `setup.ts`.
- **Graceful fallback** — every key has an English value; untranslated
  keys degrade to English, never to a raw key string.
- Translated surfaces: navbar, footer, home hero, room card, room modal,
  copilot widget, trust badges, search labels, KYC status labels.

## 3. Production-grade neural embeddings

`rooms/embedding_service.py` upgrades:

- **`SEMANTIC_EMBEDDING_MODE`** — `auto` (default), `neural`, `lite`.
  `neural` requires `sentence-transformers` and falls back to the lite
  provider with a warning when the package is missing — search never
  breaks.
- **Disk-persisted matrix** — the embedding matrix is saved to
  `SEMANTIC_EMBEDDING_CACHE_DIR` (default `MEDIA_ROOT/embeddings`) keyed by
  provider + room-data fingerprint. Every worker reuses the prebuilt
  matrix instead of re-encoding the corpus (and re-downloading the model)
  on first request.
- **`python manage.py prebuild_embeddings`** — deploy-time warm-up: builds
  and persists the index, prints the provider + room count + cache path.

## 4. E2E suite expansion (trust-flow + map)

The project's E2E concept is the Django `@tag("e2e")` suite (fraud,
payments, KYC) driven over the real API in the CI `e2e` job. Tier 3 adds:

- `chat/test_e2e_trust.py` — the full trust chain: report a payment-request
  message → duplicate-report collapse → admin queue → dismiss → block →
  new chat refused → unblock → audit trail. Also added the missing
  `report.created`, `user.blocked` and `user.unblocked` audit events the
  Phase-12 spec required.
- `rooms/test_e2e_map.py` — map search → area stats → commute ETA with the
  OSRM-off fallback path (the CI-safe default).

## 5. Tenant behavioral trust signals

`users/trust.py` computes **transparent, data-backed** signals (never
internal fraud scores):

- `completed_bookings` — approved bookings whose deposit was refunded or
  whose check-out date passed. Pending / in-progress stays never count.
- Exposed as `trust_signals` on the user-details payload, chat
  participants, and as `tenant_trust_signals` on bookings.
- Frontend renders a **✓ N completed bookings** chip in the verified-tenant
  badge, chat headers, and the dashboard booking rows — a real platform
  fact beside the identity claim, never a made-up "trust score".

## Verification

- Backend **610 tests** (578 unit + 32 tagged E2E) · Frontend **320 tests**
  · tsc + build · ruff/eslint clean.
- New backend tests: `copilot/test_listing_qa.py`,
  `rooms/test_embeddings_prod.py`, `users/test_trust_signals.py`,
  `chat/test_e2e_trust.py`, `rooms/test_e2e_map.py`.
- New frontend tests: `src/i18n/index.test.tsx`,
  `VerifiedTenantBadge` completed-bookings cases.

## Future work

- Browser-level Playwright suite on top of the tagged API E2E suite.
- Full page-by-page i18n coverage (admin panels, dashboard tabs).
- A real hosted sentence-transformer model (e.g. Hugging Face endpoint)
  with `SEMANTIC_EMBEDDING_MODE=neural` in production.
