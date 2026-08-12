# Rentora — Architecture & Technical Design

> **Audience:** engineers onboarding to the codebase, reviewers evaluating the design, and anyone planning the next phase.
> **Status:** reflects `main` (Phase 11, post `be17611`). Sections marked *"target"* describe the planned Phase 8 production shape; everything else ships today.

---

## 1. System Overview

Rentora is a **two-tier web application** — a React single-page app (SPA) talking to a Django REST API over JSON — plus a WebSocket layer for real-time chat and notifications, and an async worker layer (Celery) for scheduled maintenance and event-driven jobs.

```
┌──────────────────────────┐         ┌───────────────────────────┐
│   Frontend (React SPA)   │  HTTP   │      Backend (Django)     │
│  Vite · TS · Tailwind    │ ──────► │  DRF · Channels · Celery  │
│  MapLibre · WebAuthn     │  WS     │  JWT · 2FA · Passkeys     │
└──────────────────────────┘ ──────► └─────────────┬─────────────┘
                                                   │
                              ┌────────────────────┼────────────────────┐
                              ▼                    ▼                    ▼
                       SQLite / PostgreSQL    Redis (channel +      Payment gateways
                       (data of record)       cache + broker)       (SSLCommerz, bKash)
```

**Key architectural decisions (and the trade-offs behind them):**

| Decision | Rationale | Trade-off accepted |
| --- | --- | --- |
| Django + DRF monolith (not microservices) | 11 domain apps share one transaction boundary; a solo/early team ships faster; auth, audit and signals stay coherent | Vertical scaling limits; phase out via module boundaries, not service splits |
| React SPA + REST + WebSocket | Familiar tooling; DRF gives auto OpenAPI; Channels gives real-time without a second stack | Two languages; client-side routing must mirror backend auth state |
| SQLite dev / Postgres prod | Zero-setup local dev; parity via portable queries (full-text fallback) | SQLite-specific SQL must be avoided |
| JWT (SimpleJWT) access/refresh | Stateless, works for SPA + mobile | Token revocation needs blacklist (enabled) |
| Celery eager-by-default locally | No Redis needed for dev/CI; same code path in prod (Redis broker) | Eager mode hides race conditions (covered by tests) |
| sklearn TF-IDF + LSA (not a neural model) | Bangla+English semantic search with zero heavy deps; CI-safe | Cosine similarity < transformer quality; swappable behind `rooms/semantic.py` |

---

## 2. Backend Architecture

### 2.1 App inventory (11 domain apps)

| App | Responsibility | Key models |
| --- | --- | --- |
| `users` | Custom `User` (roles, 2FA, passkeys, KYC, referral) | `User`, `OtpChallenge`, `RecoveryCode`, `PasskeyCredential`, `KycDocument` |
| `rooms` | Listings, images, geo, search, tiers, semantic/NL | `Room`, `RoomImage`, `RoomImageHash`, `RoomView` |
| `bookings` | Booking lifecycle + reviews | `Booking`, `Review` |
| `wishlist` | Saved rooms + public share | `WishlistItem`, `WishlistShare` |
| `notifications` | In-app + email + browser push | `Notification`, `PushSubscription` |
| `dashboard` | Aggregated stats endpoints | — (queries only) |
| `chat` | Real-time conversations (Channels) | `ChatRoom`, `ChatMessage`, `Presence` |
| `payments` | SSLCommerz/bKash, refunds, tier upgrades | `Payment`, `PaymentAuditLog`, `ListingPromotion` |
| `recommendations` | Content/collaborative/hybrid + similar rooms | — (computed) |
| `pricing` | Market stats, price insight, fair-price prediction | `MarketStat` |
| `roommates` | Profiles + weighted matching | `RoommateProfile`, `RoommateRequest` |
| `fraud` | 6-detector engine + review queue | `FraudReport`, `FraudScanRun` |
| `savedsearches` | Saved filter sets + AI relevance matching + price-drop alerts | `SavedSearch` (notifications carry `meta`) |
| `audit` | Append-only event trail | `AuditLogEntry` |

> `dashboard`, `recommendations` and `pricing` are thin view layers over other apps' data — they stay separate so their API surface can evolve independently.

### 2.2 Layering convention

```
views.py      — DRF viewsets; HTTP semantics only (auth, pagination, serialization)
serializers.py — request/response contracts; validation
services.py   — business logic; called by views AND Celery tasks (single source of truth)
models.py     — schema + domain constraints; signals for cross-app reactions
tasks.py      — Celery jobs; thin wrappers over services
```

The **services layer is the contract** — views and tasks never duplicate business rules (e.g. booking status transitions live in `bookings/services.py` and are used by the API and the payment callbacks).

### 2.3 Cross-cutting concerns

| Concern | Where | How |
| --- | --- | --- |
| AuthN | `users` + `dj_rest_auth` | JWT access/refresh; OTP challenge flow; WebAuthn passkeys |
| AuthZ | DRF permissions | `IsAuthenticated`, `IsOwnerOrReadOnly`, `IsAdminUser`; role checks in views |
| Rate limiting | DRF throttles | Auth 10/hr/IP, anon 100/hr, user 1000/hr, payment 5/hr |
| Errors | `config/exceptions.py` | Consistent JSON envelope: `{error: {code, message, fields}}` |
| Audit | `audit` app | `log_action()` writes append-only rows with actor + IP; admin read-only |
| Logging | `config/logging.py` | `JSONFormatter` when `JSON_LOGS=True`; stdlib-only |
| Error tracking | Sentry | `SENTRY_DSN` set ⇒ enabled; unset ⇒ no-op (local/CI never send) |
| Sanitization | `bleach` | All user-generated HTML fields on write |

### 2.4 Auth flow (login with 2FA)

```
POST /auth/login/  ──► password check ──► 200 {pending_challenge} (masked email)
POST /auth/otp/verify/ (challenge + code) ──► 200 {access, refresh}
                              └─ or recovery_code (one-time, hashed)
Passkeys: /auth/passkey/login/begin → complete ──► same token issue path
```

Tokens are only issued **after** 2FA verification — no token leaks at the password step. OTP challenges are hashed (SHA-256), TTL 10 min, 5-attempt lockout, 30 s resend cooldown.

### 2.5 Fraud engine (defense in depth)

Every room creation triggers an **async scan** (Celery task, isolated so a detector failure can never break listing):

```
Room.save() → signal → scan task ──► 6 detectors
  • duplicate title (difflib)
  • copied description (similarity ratio)
  • price anomaly (vs market percentiles)
  • missing images
  • unverified owner (KYC status)
  • rapid spam (creation cadence)
        │
        ▼
FraudReport(severity) ──► admin review queue ──► approve/dismiss (audited + emailed)
Room.flagged=true ──► "under review" badge ──► auto-scan on listing (daily beat)
```

### 2.6 Semantic search & NL parsing (Phase 11)

```
?q=<text>&smart=1
   │
   ├─ rooms/nl_query.py     ──► budget / area / type / gender / months (Bangla+English)
   │                            digits (১০) + number words (দশ) + area aliases
   │                            (ধানমণ্ডি ২৭ → Dhanmondi, typo-tolerant: mirpore → Mirpur)
   │                            → real filters + `nl_parsed` chips for the UI
   ├─ rooms/area_aliases.py ──► canonical Bangla/English/Banglish area map (single source)
   ├─ rooms/ranking.py      ──► hybrid rank: neural embeddings × SEMANTIC_SEARCH_WEIGHT
   │                            + TF-IDF/LSA × TFIDF_SEARCH_WEIGHT, then per-user
   │                            personalization blend (reuses the recommendation profile)
   │                            — hard filters always win; cold start → plain relevance
   ├─ rooms/embedding_service.py ─► provider chain: sentence-transformers (optional)
   │                                → lite bilingual synonym-hash (zero deps) → TF-IDF → keyword
   ├─ rooms/semantic.py     ──► TF-IDF (char n-grams) → LSA → cosine rank (lexical leg)
   + rooms/image_search.py ──► pHash of primary photo → look-alike rooms
   + rooms/price_anomaly.py ──► price vs predicted market badge (reuses pricing model,
                                trained once per request)
   + rooms/listing_quality.py ─► 0-100 completeness score + suggestions (weights in
                                 LISTING_QUALITY_WEIGHTS) — detail page chip, insights
                                 column, tiny secondary ranking lift (0.05)
   + rooms/ranking.py        ──► quality lifts + fraud-risk penalty applied only inside
                                 the relevant pool (never overrides explicit intent)
```

### 2.7 Saved-search AI matcher + price-drop alerts (Phase 11+)

```
Room created / price changed
   │
   ├─ rooms/signals.py ─────► RoomPriceHistory row on every real price change
   ├─ savedsearches/tasks.py ► match_room_event (immediate) + check_saved_searches (beat digest)
   ├─ savedsearches/services.py ─► score_saved_search_match: hard filters gate FIRST,
   │                               then weighted area/price/room-type/semantic/preference/
   │                               quality score ≥ SAVED_SEARCH_MATCH_THRESHOLD (0.75)
   │                               → reasons ("✓ Matches your preferred area") + level
   ├─ notifications/utils.py ► dedupe via cooldown (SAVED_SEARCH_COOLDOWN_HOURS), meta:
   │                           {room_id, saved_search_id, level, match_score}
   └─ price-drop alert: latest_price_drop() over RoomPriceHistory ≥ 10% → alert
```

### 2.8 Voice search (Phase 11+)

No backend service: `frontend/src/hooks/useVoiceSearch.ts` wraps the browser **Web Speech API**
(bn-BD default) and drops the transcript into the existing `?q=` search input — the whole
Phase 11 pipeline (NL parser → aliases → semantic ranking → personalization → quality/fraud)
applies unchanged. Raw audio is never stored or uploaded; unsupported/denied states degrade
gracefully to text search.

The vector spaces are built **in-process and cached by fingerprint** (no external model, no index to maintain) — correct for the catalog size today, and each signal is independently disable-able (`SEMANTIC_SEARCH_ENABLED`, `FUZZY_SEARCH_ENABLED`, `AREA_ALIAS_ENABLED`, `PERSONALIZED_SEARCH_ENABLED`, `PRICE_ANOMALY_ENABLED`, `LISTING_QUALITY_SCORE_ENABLED`, `FRAUD_AWARE_RANKING_ENABLED`, `VOICE_SEARCH_ENABLED`, `SAVED_SEARCH_AI_MATCHING_ENABLED`) with graceful fallback to the next leg.

---

## 3. Frontend Architecture

### 3.1 Layer map

```
pages/          — route components (Home, Rooms, Map, Chat, Dashboard, Roommates, Auth)
components/     — feature components (RoomCard, RoomModal, SearchFilter, …)
  ui/           — shadcn/ui primitives
hooks/          — TanStack Query hooks (useRooms, useBookings, useFraudStatus, …)
services/       — typed API clients (axios + interceptors)
stores/         — Zustand (ui/theme, wishlist, notifications)
context/        — AppContext (auth session)
types/          — shared TypeScript contracts
config/         — env config (VITE_API_BASE_URL …)
```

### 3.2 State management strategy

| State | Owner | Why |
| --- | --- | --- |
| Server data | TanStack Query | caching, invalidation, retries, dedupe |
| Auth session | React context (AppContext) | single source for token + user, mounted once |
| UI prefs (dark mode) | Zustand + localStorage | persisted, no server round-trip |
| Wishlist/notifications | Zustand | optimistic updates + cross-component sync |
| URL state (filters, map viewport) | React Router search params | shareable/bookmarkable links |

### 3.3 Routing & code splitting

Routes are **lazy-loaded** (`React.lazy` + `Suspense`) so each page ships as its own chunk — the initial bundle stays small while the map, dashboard and chat load on demand. The `Map` page additionally code-splits MapLibre.

### 3.4 Error handling

- API interceptor maps HTTP status → typed errors; **401 handling is path-aware** — anonymous users hitting a public endpoint are *not* bounced to `/auth` (regression-tested).
- React error boundary forwards component stacks to Sentry when configured.
- Forms use React Hook Form + Zod; server field errors render under the matching input.

---

## 4. Data Model

### 4.1 Core domain

```
User 1───N Room 1───N RoomImage
  │                1───N RoomImageHash (pHash cache)
  ├──N Booking N───1 Room
  ├──N Review N───1 Room
  ├──N WishlistItem N───1 Room
  ├──N Notification
  ├──N Payment / ListingPromotion
  └──N FraudReport (per room)
```

### 4.2 Key constraints

- **Unique email** at DB + API + seed layers.
- Booking status is a closed set (`pending → approved/rejected/cancelled/completed`) enforced in services.
- A room can hold **one active promotion per tier** (double-click race protected).
- Audit log is **append-only** — no update/delete paths exposed.
- OTP codes, recovery codes stored **hashed**; passkeys store **public keys only**.

### 4.3 Migrations & data integrity

- All schema changes ship as numbered migrations; CI runs `makemigrations --check` so a forgotten migration fails the build.
- Backfills (referral codes, wishlist tokens) run inside the migration that introduces the field.
- DB backups: `scripts/backup_db.py` (SQLite copy via backup API / Postgres `pg_dump`, `--keep N` pruning). See `docs/ops/backup-restore.md`.

---

## 5. Real-time & Async

### 5.1 Channels

| Layer | Backend |
| --- | --- |
| Channel layer | `channels_redis` when `CHANNELS_BACKEND=redis`, else in-memory |
| Chat consumer | `chat/consumers.py` — typing, read receipts, presence, file upload (auth-gated) |
| Notifications | pushed over the same WS group (`user.<id>`) |

### 5.2 Celery

- **Broker:** `CELERY_BROKER_URL` unset ⇒ tasks run **eagerly** (synchronous, no Redis) — dev/CI identical behavior; set ⇒ real async.
- **Beat schedule** (production): hourly tier expiry, daily market-stat refresh, daily catalog fraud re-scan, daily rent reminders, daily saved-search match checks, daily KYC SLA breach alerts.
- Tasks are idempotent where repeatable (`get_or_create` date-stamped alerts; `last_checked_at` advancing) so a retried cron never stacks duplicates.

---

## 6. Payments & Monetization

```
POST /payments/initiate/ (SSLCommerz)  ──► gateway redirect
POST /payments/bkash/initiate/        ──► bKash checkout
      └─ callbacks (success|fail|cancel) ──► PaymentAuditLog + booking/tier activation
POST /payments/tier-upgrade/initiate/ ──► ListingPromotion (amount server-side)
```

- Pricing is **server-side** (client can never set the amount).
- Promotion expiry auto-reverts via `expire_listings` command + query-time `effective_tier`.
- Payments are audited (`PaymentAuditLog`); refunds are request-gated.

---

## 7. Deployment

### 7.1 Current (shipped)

- **Local dev:** `runserver` (SQLite) + Vite dev server. Zero `.env` required.
- **CI (GitHub Actions):** 5 jobs — backend tests + coverage gate, frontend tests + build, lint (ruff + ESLint + Prettier), coverage-summary PR comment, per-branch coverage history.

### 7.2 Target (Phase 8 — *"Next — CI/CD done"*)

| Component | Target |
| --- | --- |
| Containers | Docker Compose: `web` (Daphne ASGI), `worker` (Celery), `beat`, `redis`, `db` (Postgres 16) |
| TLS | Reverse proxy terminates HTTPS (Let's Encrypt) |
| Static/media | Whitenoise/`collectstatic` + object storage for uploads |
| Environments | dev / staging / prod with distinct `DJANGO_SETTINGS_MODULE` |
| Observability | Sentry + structured JSON logs shipped to a log backend |
| Rollback | Image tags pinned per release; DB migration forward-only with backup-before-deploy |

---

## 8. Quality & Testing Strategy

| Layer | Tooling | Scope |
| --- | --- | --- |
| Unit | Django `TestCase` / pytest | services, serializers, NL parser, semantic rank, fraud detectors, matching |
| API | `APITestCase` | auth flows, authorization boundaries, filters, tier gating, KYC privacy |
| E2E-ish | Django test suites (`test_e2e.py`) | fraud scan → flag → landlord email → re-scan cycle; KYC upload → review → badge |
| Frontend | Vitest + Testing Library | services, hooks, components (414 total: 229 BE + 185 FE) |
| Coverage gates | CI | BE ≥50% (≈61%), FE ≥55% (≈99%) |
| Style | ruff + ESLint + Prettier + husky/lint-staged | enforced at commit AND in CI |

---

## 9. Security Posture

- **Identity:** unique-email enforcement, zxcvbn entropy rejection + HIBP k-anonymity check on register, 2FA (email OTP, email-verified enable, recovery codes), passkeys (public-key only, sign-counter replay protection, conditional UI).
- **Trust:** KYC documents served through auth-gated endpoints (strangers get 404 — no existence leak); append-only audit trail.
- **Abuse:** fraud auto-scan on every listing; throttles on auth/payment; sanitization on all user text.
- **Transport:** CORS pinned in prod; HSTS + security headers; HTTPS planned with Phase 8.

---

## 10. Extension Points (where the next phase plugs in)

| Surface | File/module | What to add |
| --- | --- | --- |
| Semantic ranking | `rooms/semantic.py` | swap TF-IDF for a transformer embeddings service |
| NL parser | `rooms/nl_query.py` | extend area/word maps; intent slots |
| Fraud detectors | `fraud/detectors.py` | add detectors without touching the scan pipeline |
| Recommendations | `recommendations/` | history-based scoring already reads views/wishlists |
| Notifications | `notifications/` | new event types ride the same in-app + push + email fan-out |
| Chat safety | `chat/consumers.py` | real-time scam-message detection hook |

---

## 11. Development Workflow

1. Branch `feature/<name>` (or `fix/`, `docs/`) off `main`.
2. Commit locally — husky formats/lints staged files.
3. Push → open PR → CI runs 5 checks; **all must be green**.
4. Merge (squash) → coverage history appended to the `coverage-history` branch.
5. Office `main` → personal repo via an open sync PR (head = office `main`).

**Definition of Done:** tests pass (backend + frontend), coverage gates met, lint clean, migrations checked, README/docs updated, live-verified where the change is user-visible.

---

*Companion docs: [`api-reference.md`](api-reference.md) · [`ops/backup-restore.md`](ops/backup-restore.md) · [`../README.md`](../README.md)*
