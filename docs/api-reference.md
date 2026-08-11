# Rentora — API Reference

> Base URL: `http://localhost:8000/api/v1` (dev) · Interactive docs: `/api/v1/docs/` (Swagger), `/api/v1/redoc/` (ReDoc), schema at `/api/v1/schema/`.
> Auth: `Authorization: Bearer <access_token>` for authenticated endpoints.
> This reference is hand-maintained alongside the README; the OpenAPI schema at `/api/v1/schema/` is always the source of truth.

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
| GET | `/rooms/insights/` | Owner | per-listing views 7d/30d, wishlists, bookings, price vs area |
| POST | `/rooms/bulk/` | Owner | bulk listing creation |
| GET | `/rooms/tier-catalog/` | Public | tier pricing + benefits (Promote UI) |
| GET | `/rooms/:id/similar-images/` | Public | look-alike rooms via pHash |

### Room list filters

**Text:** `?q=` (full-text + typo tolerance; Postgres `pg_trgm` / SQLite `icontains` fallback)
**Smart search:** `?q=১০ হাজার এর মধ্যে uttara student room&smart=1` — NL parsing (budget/area/type/gender become filters) + semantic ranking; response carries `nl_parsed` for the "AI understood" chips.
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
| POST | `/wishlist/toggle/` | Auth | `{room: id}` → add/remove (idempotent) |
| POST | `/wishlist/share-info/` | Auth | my public share token + link |
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
| PATCH | `/saved-searches/:id/` | Auth | rename / toggle active |
| DELETE | `/saved-searches/:id/` | Auth | delete |
| POST | `/saved-searches/:id/check/` | Auth | manual "check now" for new matches |

A daily Celery beat task notifies you when a **new** matching listing appears (never re-alerts the same rooms).

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

# 3. smart search (Bangla NL → budget + area chips)
curl -s "$BASE/rooms/?smart=1&q=%E0%A6%A6%E0%A6%B6%20%E0%A6%B9%E0%A6%BE%E0%A6%9C%E0%A6%BE%E0%A6%B0%20%E0%A6%8F%E0%A6%B0%20%E0%A6%AE%E0%A6%A7%E0%A7%8D%E0%A6%AF%E0%A7%87%20%E0%A6%89%E0%A6%A4%E0%A7%8D%E0%A6%A4%E0%A6%B0%E0%A6%BE" \
  | python -m json.tool | head -30   # → nl_parsed: Budget ≤ ৳10,000 + Uttara

# 4. request a booking
curl -s -X POST $BASE/bookings/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"room": 1, "start_date": "2026-09-01", "message": "Hi, is this still available?"}'
```

---

## 18. Versioning & compatibility

- API is versioned by URL prefix (`/api/v1/`); breaking changes land under `/api/v2/`.
- The OpenAPI schema (`/api/v1/schema/`) is regenerated from the code (drf-spectacular) — treat it as canonical; this document is the curated companion.
- Field names in responses follow snake_case; the frontend maps to camelCase in `services/mappers.ts`.
