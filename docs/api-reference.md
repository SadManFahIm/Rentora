# Rentora — API Reference

> Base URL: `http://localhost:8000/api/v1` (dev) · Interactive docs: `/api/v1/docs/` (Swagger), `/api/v1/redoc/` (ReDoc), schema at `/api/v1/schema/`.
> Auth: `Authorization: Bearer <access_token>` for authenticated endpoints.
> This reference is hand-maintained alongside the README; the OpenAPI schema at `/api/v1/schema/` is always the source of truth.
> **Live-verified:** every endpoint below is checked against a running server on four layers — status code, **deep JSON schema** (required fields + wire types), **request-body contracts** (payloads validated against documented field names/types, plus malformed-payload probes asserting the right field error) and **OpenAPI cross-check** (every tested path must exist in `/api/v1/schema/`). Response and request contracts are **auto-generated from the live OpenAPI schema at runtime** — no hand-maintained tables to drift; a small override table handles only genuinely ambiguous shapes (e.g. `allOf` inheritance, `SerializerMethodField` types). Re-run anytime with `python docs/tools/api-verify.py`.
>
> Auto-generation also caught and fixed **real backend schema bugs**: `SerializerMethodField`-backed fields (`is_featured`, `passkeys`) mis-declared as `string`, action endpoints (`summary`, `tier-catalog`, `insights`, `bulk`, reviews `summary`) declaring the wrong 200 response schema, and nullable fields not honoring `null` in wire responses.
>
> **Frontend contract check:** the frontend's hand-written wire types (`frontend/src/services/mappers.ts`) are typechecked against these schemas in CI (`openapi-typescript` generates `frontend/src/generated/openapi.d.ts` from the live schema, then `tsc -p frontend/tsconfig.contract.json` asserts each generated component satisfies the corresponding wire type via `frontend/src/lib/schemaContract.ts`). A field rename/removal or incompatible type change fails the PR. **Schema-drift PR comment:** every PR's head schema is diffed against base by `docs/tools/schema-drift.py` and a sticky comment lists any endpoint/component changes (doc-only changes are ignored).

---

## 1. Conventions

- **Errors** always return a JSON envelope:
  ```json
  { "error": { "code": "validation_error", "message": "…", "fields": { "email": ["Enter a valid email address."] } } }
  ```
- **Pagination** (list endpoints): `?page=N` → `{count, next, previous, results}`.
- **Filters** compose: `?area=Dhanmondi&room_type=studio&price__gte=5000&price__lte=15000&is_available=true&q=cozy&ordering=-price&owner=3`.
- **Throttling:** auth 10/hr/IP · anonymous 100/hr · authenticated 1000/hr · payment initiation 5/hr.

### 1.1 Status codes you will actually see

| Code | Meaning |
| --- | --- |
| 200 / 201 | OK / created |
| 204 | Deleted (no body) |
| 400 | Validation / malformed request |
| 401 | Missing/invalid token — or OTP challenge pending |
| 403 | Authenticated but not allowed (wrong role / not owner) |
| 404 | Not found (also used to hide KYC docs from non-owners) |
| 429 | Rate limited |

---

## 2. Authentication

### Register
`POST /auth/register/` — Public
```json
{ "username": "new.tenant", "email": "new.tenant@rentora.com", "password1": "…", "password2": "…" }
```
- Email must be **unique** (API + DB enforced). `?ref=CODE` attributes a referral.
- Password checked by zxcvbn entropy (rejects trivially guessable) + HIBP k-anonymity warning.

### Login
`POST /auth/login/` — Public → `{ "access", "refresh" }` **or** `{ "pending_challenge": "r***@rentora.com" }` for 2FA accounts (no tokens at this step).

### Finish 2FA login
`POST /auth/otp/verify/` — Public
```json
{ "challenge_id": "…", "code": "123456" }        // emailed code
{ "challenge_id": "…", "recovery_code": "…" }   // one of 10 one-time backups
```
→ `{ "access", "refresh" }`

### Refresh / Logout / Me
| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/auth/token/refresh/` | Public | `{refresh}` → new access |
| POST | `/auth/logout/` | Auth | blacklists the refresh token |
| GET/PATCH | `/auth/user/` | Auth | current profile; PATCH updates profile fields |

### 2FA management
| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/auth/otp/toggle/` | Auth | disable, or begin enabling (password → emailed code) |
| POST | `/auth/otp/confirm-enable/` | Auth | confirms emailed code → 2FA on + 10 recovery codes returned once |
| POST | `/auth/otp/resend/` | Public | 30 s cooldown |

### Passkeys (WebAuthn)
| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/auth/passkey/register/begin/` | Auth | ceremony options |
| POST | `/auth/passkey/register/complete/` | Auth | stores public key + counter |
| POST | `/auth/passkey/login/begin/` | Public | returns `challenge_id` (conditional UI) |
| POST | `/auth/passkey/login/complete/` | Public | assertion → JWTs (or pending OTP for 2FA) |

---

## 3. Rooms

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/rooms/` | Public | list (see filters below) |
| GET | `/rooms/:id/` | Public | detail + geo annotations (`distance_km`) |
| POST | `/rooms/` | Auth | create (triggers fraud auto-scan) |
| PUT/PATCH | `/rooms/:id/` | Owner | update |
| DELETE | `/rooms/:id/` | Owner | delete |
| GET | `/rooms/landmarks/` | Public | universities 🎓 / metro 🚇 for map layers |
| GET | `/rooms/summary/` | Public | `COUNT/AVG` for the current viewport — powers the "N of M in view" badge |
| GET | `/rooms/geocode/?q=` | Public | gazetteer + Nominatim fallback |
| GET | `/rooms/insights/` | Auth (own listings) | per-listing views 7d/30d, wishlists, bookings, price vs area, listing quality score |
| POST | `/rooms/bulk/` | Auth | bulk listing creation (JSON array body, per-row errors) |
| GET | `/rooms/tier-catalog/` | Public | tier pricing + benefits (Promote UI) |
| GET | `/rooms/:id/similar-images/` | Public | look-alike rooms via pHash |

### Room list filters

**Text:** `?q=` (full-text + typo tolerance; Postgres `pg_trgm` / SQLite `icontains` fallback)
**Smart search:** `?q=১০ হাজার এর মধ্যে uttara student room&smart=1` — NL parsing (budget/area/type/gender become filters) + **hybrid ranking**: neural embeddings (optional `sentence-transformers`, or the built-in bilingual lite provider) blended with TF-IDF/LSA at `SEMANTIC_SEARCH_WEIGHT`/`TFIDF_SEARCH_WEIGHT`; typo-tolerant **area aliases** (`mirpore` → Mirpur, `ধানমণ্ডি ২৭` → Dhanmondi); per-user **personalization** for signed-in tenants (relevance + `PERSONALIZATION_WEIGHT` blend, hard filters always win). Response carries `nl_parsed` for the "AI understood" chips; `?debug_rank=1` (debug builds only) adds `rank_meta` with per-room semantic/lexical/personalization/final scores.

**List card field — `price_anomaly`** (optional, nullable): `{available, predicted_price, difference_percentage, direction: above_market|below_market, badge}` — rendered only when the fair-price model is confident and `|actual − predicted| / predicted ≥ PRICE_ANOMALY_THRESHOLD`. Disable with `PRICE_ANOMALY_ENABLED=false`.

**Detail field — `listing_quality`** (always present): `{score: 0-100|null, level: excellent|good|fair|needs_improvement|poor|null, category_scores, suggestions: string[]}` — a transparent completeness score (never a valuation or fraud score). Disable with `LISTING_QUALITY_SCORE_ENABLED=false`.

**Smart ranking — quality + fraud secondary signals** (`?q=...&smart=1`): within the already-relevant pool, listing quality lifts (`LISTING_QUALITY_RANKING_WEIGHT=0.05`) and the existing fraud engine's risk score demotes (`FRAUD_AWARE_RANKING_ENABLED`, `FRAUD_RANKING_PENALTY_WEIGHT=0.20`). `?debug_rank=1` shows `quality_score` and `fraud_risk` per room in `rank_meta`.
**Geo:**
```
?bbox=min_lng,min_lat,max_lng,max_lat     map viewport
?near_lat=23.75&near_lng=90.39&radius_km=2
?near_landmark=mirpur-10-metro&radius_km=3
```
**Facets:** `?area=` · `?room_type=single|shared|studio` · `?price__gte=` · `?price__lte=` · `?is_available=true` · `?verified=true` (KYC-approved owners only) · `?amenities=wifi,ac` · `?gender=male|female` · `?ordering=price|-price|-created|match` · `?owner=:id` · `?history=1` (personal ranking boost from views/wishlists).

---

## 4. Bookings

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/bookings/` | Auth | mine (tenant + landlord views) |
| POST | `/bookings/` | Auth | request a booking |
| PATCH | `/bookings/:id/` | Auth | status update — role-gated transitions (`pending → approved/rejected/cancelled/completed`) |

Creating/updating a booking fires notifications (in-app + email + browser push) and the landlord dashboard counters.

---

## 5. Reviews

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/reviews/?room=:id` | Public | reviews for a room |
| POST | `/reviews/` | Auth | requires an approved booking (verified-stay badge) |
| GET | `/reviews/summary/?room=:id` | Public | 5★ histogram + average + verified-stay counts |

Reviews support **landlord replies** and **photo attachments** (Phase 10).

---

## 6. Wishlist

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/wishlist/` | Auth | my saved rooms |
| POST | `/wishlist/toggle/` | Auth | `{room_id: <int>}` → add/remove (idempotent) |
| GET | `/wishlist/share-info/` | Auth | my public share token + link |
| GET | `/wishlist/share/:token/` | Public | read-only room summaries; 404 on unknown token (no enumeration) |

---

## 7. Notifications

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/notifications/` | Auth | my notifications (newest first) |
| PATCH | `/notifications/:id/` | Auth | mark read |
| POST | `/notifications/mark-all-read/` | Auth | — |
| GET | `/notifications/unread-count/` | Auth | badge counter |
| POST | `/notifications/push/subscribe/` | Auth | register a browser push subscription (VAPID) |

Every in-app notification is fanned out to email (branded template) + browser push when subscribed.

---

## 8. Saved Searches (Phase 10)

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/saved-searches/` | Auth | my saved searches |
| POST | `/saved-searches/` | Auth | save current filter set `{name, filters}` |
| DELETE | `/saved-searches/:id/` | Auth | delete (rename/toggle-active update endpoint not exposed) |
| POST | `/saved-searches/:id/check/` | Auth | manual "check now" for new matches |

A daily Celery beat task notifies you when a **new** matching listing appears (never re-alerts the same rooms).

**AI matching (Phase 11+)** — since `SAVED_SEARCH_AI_MATCHING_ENABLED=true` (default), alerts are relevance-gated: hard filters always gate first (area/budget/type/gender), then a weighted score (`SAVED_SEARCH_MATCH_WEIGHTS`) must clear `SAVED_SEARCH_MATCH_THRESHOLD` (0.75) to notify, with plain-language reasons (`✓ Matches your preferred area`). A room **create/price-change** event task (`match_room_event`) alerts immediately; a ≥ `PRICE_DROP_NOTIFICATION_THRESHOLD` (10%) price cut (tracked via `RoomPriceHistory`) triggers a price-drop alert for matching searches; the per-user/room **cooldown** (`SAVED_SEARCH_COOLDOWN_HOURS` = 24) dedupes repeats. Notifications carry `meta: {room_id, saved_search_id, level, match_score}`.

---

## 9. Dashboard

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/dashboard/stats/` | Auth | tenant + landlord aggregates (bookings, revenue, ratings, listings) |

---

## 10. Chat

| Method / WS | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET/POST | `/chat/rooms/` | Auth | list / create chat rooms |
| GET | `/chat/rooms/:id/messages/` | Auth | message history |
| POST | `/chat/rooms/:id/messages/` | Auth | send |
| GET | `/chat/online-status/` | Auth | presence |
| POST | `/chat/upload/` | Auth | attachment (auth-gated file) |
| WS | `/ws/chat/:room_id/` | Auth | real-time: typing, read receipts, presence |

---

## 11. Payments & Tiers

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/payments/initiate/` | Auth | SSLCommerz checkout |
| POST | `/payments/bkash/initiate/` | Auth | bKash checkout |
| POST | `/payments/bkash/callback/` | Public | gateway callback |
| POST | `/payments/sslcommerz/success\|fail\|cancel/` | Public | gateway callbacks (audited) |
| GET | `/payments/` | Auth | my payment history |
| GET | `/payments/:id/` | Auth | detail / receipt |
| POST | `/payments/:id/refund/` | Auth | request refund |
| GET | `/payments/summary/` | Auth | totals by period |
| POST | `/payments/tier-upgrade/initiate/` | Owner | Featured ৳199/30d · Premium ৳499/30d (amount server-side) |

Tier ordering at query time: **Premium → Featured → Verified → Free**, with `effective_tier` reverting expired promotions automatically.

---

## 12. Recommendations & Pricing (AI)

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/recommendations/?limit=N` | Auth | hybrid (content + collaborative) personal picks |
| GET | `/recommendations/similar/:room_id/` | Public | content-based similar rooms — area/type/price/amenity overlap, match % + reasons |
| POST | `/pricing/predict/` | Auth | fair-price prediction for a new listing |
| GET | `/pricing/insight/:room_id/` | Public | price vs area market position |
| GET | `/pricing/market-stats/?area=X&room_type=Y` | Public | raw market stats |

---

## 13. Roommates

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET/PUT | `/roommates/profile/` | Auth | get / upsert my profile |
| GET | `/roommates/matches/` | Auth | weighted best-first matches (budget/area/type/gender/lifestyle) |
| GET/POST | `/roommates/requests/` | Auth | list / send request |
| POST | `/roommates/requests/:id/action/` | Receiver | approve / reject |

---

## 14. Fraud Detection

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/fraud/rooms/:room_id/status/` | Public | badge data ("under review") |
| GET | `/fraud/reports/` | Auth | owner: own rooms; admin: all — `?status=` `?severity=` |
| POST | `/fraud/rooms/:room_id/scan/` | Owner/Admin | re-run detectors |
| POST | `/fraud/reports/:report_id/review/` | Admin | mark reviewed / dismissed (audited + emailed) |

---

## 15. KYC Verification

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/users/kyc/documents/` | Auth | my documents (admin: all) |
| POST | `/users/kyc/documents/` | Auth | upload NID/passport (multipart, 5 MB cap) |
| GET | `/users/kyc/documents/:id/file/` | Owner/Admin | **auth-gated** file — strangers 404 (no existence leak) |
| GET | `/users/kyc/pending/` | Admin | review queue |
| POST | `/users/kyc/:user_id/review/` | Admin | approve/reject → badge sync + audit + notification + fraud signal clear (atomic) |
| GET | `/users/kyc/audit/` | Admin | full decision trail (who/when/note) |
| GET | `/users/kyc/sla/` | Admin | queue health: pending, avg hours, 7-day trend, breach flags, 30-day trend |

---

## 16. Referral (Phase 10)

| Method | Endpoint | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/users/referral/` | Auth | my code, invite link, joined users |

Signups landing with `?ref=CODE` on register are attributed automatically.

---

## 17. Example flows (copy-paste curl)

**Register → login → list rooms → book:**

```bash
BASE=http://localhost:8000/api/v1

# 1. register (unique email)
curl -s -X POST $BASE/auth/register/ -H "Content-Type: application/json" \
  -d '{"username":"tester.one","email":"tester.one@rentora.com","password1":"Sup3rS3cret!","password2":"Sup3rS3cret!"}'

# 2. login
TOKEN=$(curl -s -X POST $BASE/auth/login/ -H "Content-Type: application/json" \
  -d '{"username":"tester.one","password":"Sup3rS3cret!"}' | python -c "import sys,json;print(json.load(sys.stdin)['access'])")

# 3. smart search (Bangla NL → budget + area chips; hybrid semantic ranking)
curl -s "$BASE/rooms/?smart=1&q=%E0%A6%A6%E0%A6%B6%20%E0%A6%B9%E0%A6%BE%E0%A6%9C%E0%A6%BE%E0%A6%B0%20%E0%A6%8F%E0%A6%B0%20%E0%A6%AE%E0%A6%A7%E0%A7%8D%E0%A6%AF%E0%A7%87%20%E0%A6%89%E0%A6%A4%E0%A7%8D%E0%A6%A4%E0%A6%B0%E0%A6%BE" \
  | python -m json.tool | head -30   # → nl_parsed: Budget ≤ ৳10,000 + Uttara
# typo-tolerant: mirpore → Mirpur area chip
curl -s "$BASE/rooms/?smart=1&q=mirpore" | python -m json.tool | head -20

# 4. request a booking
curl -s -X POST $BASE/bookings/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"room": 1, "start_date": "2026-09-01", "message": "Hi, is this still available?"}'
```

---

## 18. Versioning & compatibility

- API is versioned by URL prefix (`/api/v1/`); breaking changes land under `/api/v2/`.
- The OpenAPI schema (`/api/v1/schema/`) is regenerated from the code (drf-spectacular) — treat it as canonical; this document is the curated companion.
- Field names in responses follow snake_case; the frontend maps to camelCase in `services/mappers.ts`.
