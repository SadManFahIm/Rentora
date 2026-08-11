# 🏠 Rentora — AI-Powered Room Rental Platform

> Bangladesh's smartest room rental platform. Find verified, affordable rooms with AI-powered recommendations, real-time chat, secure payments, roommate matching, and fraud detection.

[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6?logo=typescript)](https://typescriptlang.org)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![DRF](https://img.shields.io/badge/DRF-3.15-a30000?logo=django)](https://www.django-rest-framework.org/)
[![Tests](<https://img.shields.io/badge/tests-414%20(229%20BE%20%2B%20185%20FE)-success>)](https://github.com/SadmaFaahiim/Rentora/actions)
[![Coverage](https://img.shields.io/badge/coverage-BE%2060%25%20%E2%80%A2%20FE%2099%25-success)](https://github.com/SadmaFaahiim/Rentora/actions)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions)](https://github.com/SadmaFaahiim/Rentora/actions)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📚 Table of Contents

- [Product Overview](#-product-overview)
- [Changelog — Phase 9 · 10 · 11](#changelog)
- [What's New in v2.0](#changelog--whats-new-in-v20)
- [Delivery Roadmap](#-delivery-roadmap)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Quality Engineering](#-quality-engineering)
- [Getting Started](#-getting-started)
- [API Endpoints](#-api-endpoints)
- [Documentation](#documentation)
- [Security](#-security)
- [Passkeys / WebAuthn](#-passkeys--webauthn--shipped)
- [Demo Users](#-demo-users)
- [Screenshots](#-screenshots)
- [Team Workflow](#-team-workflow)
- [Developer](#-developer)
- [License](#-license)

---

## 📋 Product Overview

|                     |                                                                                                                                                                                               |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Problem**         | Finding a trustworthy room in Dhaka is hard — listings are scattered, landlords are hard to verify, and scams are common.                                                                     |
| **Solution**        | One verified marketplace: AI-scanned listings, real-time landlord chat, secure gateway payments, roommate matching, and an ML-powered fraud engine that catches bad actors before tenants do. |
| **Target users**    | Tenants (students & young professionals) and landlords in Bangladesh.                                                                                                                         |
| **Differentiators** | Fraud-engineered trust layer, AI recommendations & fair-price insight, roommates (a growth hook competitors lack), and a monetized listing-tier system (Free → Featured → Premium).           |

---

## 🆕 Changelog

**Phase 9 — Operate It (Reliability & Observability)**

- **Sentry error tracking** — backend (Django/Celery integrations) and frontend (`@sentry/react`); initialised from `SENTRY_DSN` / `VITE_SENTRY_DSN` and a **no-op when unset**, so local dev and CI never send events. Frontend error boundary forwards component stacks.
- **Structured JSON logging** — a stdlib-only `JSONFormatter` (`config/logging.py`) emits one JSON object per line when `JSON_LOGS=True`; stable keys (timestamp/level/logger/message) plus caller extras, ready for any log shipper.
- **Celery + Celery Beat** — `config/celery.py` with a **zero-config local mode**: an empty `CELERY_BROKER_URL` runs tasks eagerly (synchronously, no Redis), production sets a Redis broker and tasks go async. Scheduled maintenance moved onto the beat schedule: hourly tier expiry, daily market-stat refresh, daily catalogue fraud re-scan, daily rent reminders (`rooms/pricing/fraud/payments/tasks.py`).
- **Fraud hardening** — the auto-scan now runs through a Celery task wrapped in try/except so a detector or queue failure can **never break room creation**; individual detector failures are isolated (logged + skipped, the rest still run); the flag path now also emails the landlord.
- **Branded HTML transactional emails** — `notifications/emails.py` + `notifications/templates/emails/` (base shell + OTP code, recovery codes, booking status, fraud flag, promotion expiry), each with a plain-text fallback. Wired into OTP delivery, 2FA-enable recovery codes, booking lifecycle signals, fraud flags, and `expire_listings`.
- **Audit log** — new `audit` app: an append-only `AuditLogEntry` table records who did what to which object (with IP) for sensitive actions. Wired into fraud-report review and 2FA enable/disable; the Django admin view is read-only so the trail cannot be rewritten.
- **Backup & restore runbook** — `scripts/backup_db.py` (cross-platform; SQLite consistent copy via the backup API, PostgreSQL via `pg_dump`, pruning with `--keep`) plus `docs/ops/backup-restore.md` covering restore, media, and a quarterly restore drill.
- **KYC SLA breach alerts** — a daily Celery beat task (`alert_kyc_sla_breaches`) watches the KYC review queue and alerts every admin (in-app notification + branded email) when a **breach** fires: an application stuck past 48h, or decisions this week trailing last week. Deduplicated atomically per day per condition (`get_or_create` on a date-stamped title), so a retried cron never stacks identical alerts.

**Phase 10 — Grow It (Growth & Personalization)**

- **AI recommendations v2 — Similar Rooms** — every room modal now shows a **content-based similar-rooms carousel** (`GET /recommendations/similar/<id>/`): listings ranked by area, room type, price band and amenity overlap, with a match % and explainable reasons ("Same area: Dhanmondi · Similar amenities"). Same feature vector family as the personalized recommendations, so the two surfaces agree.
- **Search v2 — full-text + typo tolerance** — room search (`?q=`) is now real full-text on **PostgreSQL** (`SearchVector`/`SearchRank` with stemming + `pg_trgm` fuzzy similarity so typos still match) with an automatic **`icontains` fallback on SQLite**, so dev/CI/prod behave identically. `?q=` still composes with area/price/gender filters and geo queries.
- **Saved searches + alerts** — the Rooms page gets a **Saved searches** bar: save the current filters (with a name), and a daily Celery beat task (`check_saved_searches`) notifies you in-app whenever a **new** matching listing appears (never re-alerts the same rooms — `last_checked_at` advances every run). Manual "check now" from the list too.
- **Browser push notifications** — subscribe once from the Dashboard (**Browser notifications** card) and every in-app notification (bookings, chat, fraud flags, KYC decisions, saved-search matches) is also **pushed to your browser even when Rentora is closed**. VAPID keys generated by `scripts/generate_vapid.py` (`pywebpush` server-side + `public/sw.js` service worker); dead subscriptions are auto-pruned (410 Gone), and no VAPID = safe no-op for local dev/CI.
- **Referral program** — every account gets a unique referral code; share your **invite link** (Dashboard → **Invite friends** card, with WhatsApp/Facebook shortcuts) and signups landing with `?ref=CODE` are attributed to you (`GET /users/referral/` shows your code, link and who joined). `ref` is optional at register — the code is just a query param on the shared URL.
- **Wishlist sharing** — one tap **Share wishlist** copies a public, unguessable link (`/wishlist/share/<token>/`) — room summaries only, no personal info, 404 on bad tokens so they can't be enumerated.
- **Landlord tools — listing insights** — new Dashboard **Insights** tab: per-listing engagement (**views 7d/30d** tracked from room-detail visits, deduplicated), wishlist saves, booking requests vs approvals, and **price vs area-average** positioning (from the market-stats table) with a red/green delta badge — plus bulk listing creation (`POST /rooms/bulk/`).
- **Reviews v2 — replies, photos, rating breakdown** — reviews now support **landlord replies** (inline form for the room owner, shown under the review), **tenant photo reviews**, and the room modal shows a **rating breakdown** (5★ histogram + average + verified-stay badges) from `GET /reviews/summary/?room=`.
- **Engineering** — 388 automated tests (210 backend + 178 frontend), ruff/eslint/prettier clean, migrations include a backfill so every existing account gets a unique referral code + wishlist token.

---

## 🆕 Changelog — What's New in v2.0

**Paid Listing Tiers (first revenue stream)**

- Free → **Featured** (৳199/30d) → **Premium** (৳499/30d) promotion payments via SSLCommerz/bKash
- Server-side pricing, ownership + duplicate-tier guards, double-click race protection, premium-first search ordering
- Expired promotions auto-revert to Free (`expire_listings` command + query-time `effective_tier`)
- Dashboard **Listings** tab with Promote modal; gold/orange tier badges on cards

**Roommate Matching** — weighted scoring (budget/area/room-type/gender/lifestyle) with request/approve flow

**Fraud Detection** — 6-detector engine (duplicate title, copied description, price anomaly vs market percentiles, missing images, unverified owner, rapid spam) with auto-scan + admin review queue**Auth & Trust**

- Fresh **login/register redesign** (animated Dribbble-style auth page)
- **Deep password strength meter** — zxcvbn-ts engine: real entropy (`~10^N` guesses), common-password detection ("top-10 common password" warnings), 4-segment meter, live confirm-match indicator
- **HaveIBeenPwned breach check** — k-anonymity lookup (only the first 5 chars of the SHA-1 hash leave the device); shows ⚠️ breached / ✓ safe / unknown status on the register form**Two-Factor Authentication (email OTP)**
- Password + one-time code — enabled per account from the Dashboard; **enabling is email-verified**: password first, then a code emailed to the address must be confirmed, so an account can never be locked behind an unreachable inbox
- **10 one-time recovery codes** minted at enable (shown exactly once, stored hashed) — sign in with one if you lose email access; deleted when 2FA is disabled
- OTP codes stored **hashed** (SHA-256) in the DB; 10-minute TTL, 5-attempt lockout, 30s resend cooldown, stale challenges auto-invalidated on re-login
- Login returns a pending challenge (masked destination, e.g. `r***@rentora.com`); tokens are only issued after the code verifies — no tokens leak at the password step

**Passkeys (WebAuthn / FIDO2)**

- Passwordless sign-in with a fingerprint, face, or device PIN — `py_webauthn` server-side, `@simplewebauthn/browser` client-side
- **Conditional UI** on the login form: passkeys surface in the browser's native autofill; a manual "Sign in with a passkey" button is the fallback
- Only **public keys** stored; sign counters tracked for clone/replay protection; 2FA-enabled accounts still get the email-OTP step after the passkey
- Register/revoke from the Dashboard → Security → Passkeys
- Sign in with **username or email**; **duplicate-email registration now blocked** (serializer + DB unique constraint) with a readable error message
- Already-logged-in users are redirected from `/auth` to their dashboard

**Interactive Map (Phase 7)**

- **MapLibre GL JS** map of Dhaka — OpenStreetMap tiles, key-free, with dark/light tile switching that follows the app theme
- **Price marker pins** — every listing is a tappable pin showing its price (`৳12k`), coloured by tier (free orange / featured blue / premium amber) so promoted rooms pop exactly like the list
- **Marker clustering** — with many listings in view, pins collapse into numbered cluster circles that show the **room count + average rent** (click one for a count/price-range popup, then it zooms in); toggle between **Clustered** and **Pins** modes
- **Viewport sync** — panning/zooming refetches rooms inside the visible `bbox` (debounced 300ms), so the map and the room count always match what's on screen
- **Radius search** — click a point on the map (or a university chip) and drag a slider to see rooms within 0.5–5 km, powered by the geo backend's `near_lat`/`near_lng` + `radius_km`
- **Travel-time overlay** — with a search point active, toggle **Travel** to draw walking isochrones (10/20/30 min bands, green → amber → red) so tenants see how far they can get on foot from a university, metro or office
- **Street search + autocomplete** — type a street, area or station ("gulshan", "mirpur road", "shahbagh") and pick a suggestion to fly there and start a radius search, powered by the curated Dhaka gazetteer **with an OpenStreetMap Nominatim fallback** (`/rooms/geocode/`) so even streets outside the curated list geocode
- **Get Directions + travel-mode toggle** — every room popup shows walking **and** driving ETA ("≈ 8 min walk · ≈ 2 min drive") plus a 🚶 **Walk** / 🚗 **Drive** / 🚇 **Transit** picker that opens Google Maps with the right route pre-filled (origin = your search point)
- **Metro ETA in popups** — each popup lists the nearest MRT station with distance + walking time ("🚇 Kawran Bazar MRT · 2.0 km · ≈ 27 min walk") from the backend's `proximity` annotation
- **Area count chips** — the current viewport's areas appear as tappable chips with live room counts ("Dhanmondi 3 · Mirpur 3") from `/rooms/summary/` `by_area`; tap one to fly there and start a radius search
- **Metro route corridor** — MRT Line 6 is drawn as a polyline through its stations (Uttara → Motijheel), visible with the Metro toggle or whenever the travel overlay is active; stations within a 30-minute walk of the search point get a highlighted ring
- **Room-count API badge** — the "N of M rooms in view" badge reads the authoritative server count (`/rooms/summary/` — COUNT/AVG with the same geo filters), so it is never capped by list pagination
- **Distance markers** — every listing in a radius search shows `formatDistance` + walking time ("1.2 km away · ≈ 16 min walk") in its map popup and the side list, from the backend's `distance_km` annotation
- **Viewport bbox cache** — the refetch bbox is quantized to ~100 m, so micro-pans hit the React Query cache instead of firing duplicate API calls
- **Landmark layers** — toggle universities 🎓 and metro stations 🚇 on/off as map layers (from `/rooms/landmarks/`)
- **Price heatmap** — green → amber → red circles scaled by rent, so expensive areas are visible at a glance
- **Map + list split view** — a viewport-synced sidebar lists the rooms on screen (promoted first, then by price); on mobile it becomes a bottom sheet
- Tapping a pin opens the room popup → full **RoomModal** (booking, chat, fraud badge, AI price insight)
- **Shareable map URLs** — the current viewport (center + zoom + radius search) is live-synced to the URL (`/map?center=23.81,90.41&zoom=12&r=23.78,90.40,2.0`), so you can copy the address and share an exact map view; the **Share** button copies the link, and opening a shared link restores the exact view, radius and area chips
- **Readable in both themes** — dark tiles are the CARTO CDN; if it's unreachable the map auto-falls back to dimmed OSM tiles (street labels stay legible), and the travel overlay + legend are styled for light _and_ dark

**Listing Location Picker (landlord)**

- **List a Room** now opens a proper form with a **map picker** — click the map to pin the exact listing location (or "Use my location")
- Coordinates are stored as `lat`/`lng`, powering the map view, geo search and price insight

**KYC Verification + Verified Landlord Badge**

- **Identity document upload** — landlords upload a NID or passport (image/PDF, 5 MB cap) from **Dashboard → KYC** (`KycCard`); uploads are stored server-side and **served through an auth-gated endpoint** (owner/admin only — the public media URL can never leak a document, and other users get a 404 so no existence leak)
- **Admin review panel** — pending applications queue (``GET /users/kyc/pending/``) with approve/reject; a decision flips `nid_verified`, **syncs every listing badge** via signals, resolves the pending documents, writes an **audit-log entry** (`kyc.approved` / `kyc.rejected`) and notifies the landlord — all inside one `transaction.atomic()` block
- **KYC audit trail** — Dashboard → KYC → History lists every decision (who, when, note) straight from the append-only audit log
- **Verified badge everywhere** — RoomCard pill, RoomModal, Roommates match cards, and **Chat** (shield next to a verified participant's name); verified-first ranking inside each tier
- **"Verified landlords only" filter** — one toggle on the Rooms page (`?verified=true`) narrows results to KYC-approved owners
- **E2E coverage** — upload → 403 for non-admin → queue → approve (badge flip + audit + notification + fraud signal clears) → reject with note → **reject → re-upload → approve full loop** (the landlord sees the reviewer's note on their rejected doc, re-submits, and the badge finally lands — the audit trail tells the whole story) → revoke flips back → privacy (404 for strangers) → file-type guard: 12 KYC tests
- **Rejection UX** — the dashboard KycCard shows a **"Why it was rejected"** banner with the reviewer's note (e.g. *"Blurry scan — please re-upload"*) plus the upload form, so the landlord knows exactly what to fix before re-submitting
- **Rejection email** — a rejection also sends a **branded transactional email** (`kyc_rejected` template) with the reviewer's note and a **direct re-upload CTA** that deep-links to the dashboard KYC tab, so the landlord can fix and resubmit without hunting through the app
- **KYC review SLA stats** — the admin panel now opens with a **queue-health strip**: pending applications (with the oldest-waiting age), average review time (all-time + this week), and a 7-day decision trend (`▲ +N / ▼ -N` vs last week), all from `GET /users/kyc/sla/` (admin-only)
- **SLA breach badges** — when a breach fires the strip grows **red alert chips** ("Application waiting >48h" / "Decisions down vs last week"), matching the flags the daily beat alert emails about — dashboard and alerts never disagree (same thresholds)
- **30-day decision trend chart** — the admin History tab now opens with a lightweight **dependency-free SVG chart**: daily decision counts (bars) + average review hours (line) over the last 30 days, bucketed server-side with `TruncDate`

**Engineering**

- **Coverage history per branch** — every PR and main push appends its own `history-<branch>.csv` + SVG chart to the `coverage-history` branch (viewable `index.html` linking all branches)
- 414 automated tests (229 backend + 185 frontend) · coverage gates (BE ≥50%, FE ≥55%)
- Ruff + ESLint + Prettier with husky/lint-staged pre-commit hooks
- GitHub Actions CI (backend, frontend, **live API contract check**, lint, coverage-summary PR comment, per-branch coverage history)
- Route-level code splitting (React.lazy) — smaller bundles

**Search & Discovery (Phase 11) — ✨ AI Smart Search**

- **AI Search toggle** — the Rooms page's search bar grows a gradient **✨ AI Search** button; flip it on and the box accepts *natural language*: "১০ হাজার এর মধ্যে uttara student room" is understood as **budget ≤ ৳10,000 in Uttara** (and "জুলাই move-in" as a July move-in date)
- **Bangla + English natural-language parser** (`rooms/nl_query.py`) — Bangla digits (০-৯), **number words** (দশ/বিশ/ত্রিশ… with হাজার/লাখ/কোটি multipliers — "দশ হাজার" → ৳10,000), ৳/টাকা/tk/taka, **area names in both scripts** (Uttara *and* উত্তরা, Dhanmondi *and* ধানমন্ডি — from the gazetteer's new Bangla aliases), room-type/gender words and month names in both scripts; the parsed budget/area/type/gender become **real filters**, and the list response carries an `nl_parsed` object
- **"AI understood" chips** — under the search bar the backend's interpretation renders as tappable-looking pills (`Budget ≤ ৳10,000` · `Uttara` · `move-in July`) so tenants see exactly what was understood
- **Semantic ranking** — a lightweight vector-space model (scikit-learn TF-IDF character n-grams + LSA, no heavy ML deps, works for both scripts) ranks keyword/NL-filtered rooms by cosine similarity; **semantic discovery** surfaces relevant rooms even when the query shares no literal keyword ("student room near campus" finds the student listings)
- **Personal ranking boost** — for signed-in tenants the default browse order floats rooms they recently viewed or wishlisted to the top (30-day window), layered under the paid-tier/verified ranking
- **Look-Alike Rooms (visual search)** — every RoomModal now shows a "Look-Alike Rooms" strip: rooms whose primary photo looks like the current one, via 64-bit **perceptual hashes (pHash)** computed with Pillow and cached in a new `RoomImageHash` table (mtime-keyed, so replaced photos re-hash automatically); `GET /rooms/{id}/similar-images/`
- **Dhaka coverage expanded** — the listing `Area` choices now span **20 areas** (Uttara, Tejgaon, Badda, Rampura, Banasree, Khilgaon, Motijheel, Old Dhaka, Bashundhara, Lalmatia, Shyamoli, Savar, Keraniganj, Tongi + the original 6) and the map gazetteer gained **40+ new streets/roads** (Panthapath, Bailey Road, Hatirjheel, Badda Link Road, Khilgaon Flyover, Uttara Sectors 10/12/14, Gulshan 1/2 circles, Jashimuddin Avenue …) plus 9 more universities (Jagannath, Dhaka Medical College, AUST, DIU, Stamford, UIU …) — all searchable from the map box and the NL parser
- **Bug fixes along the way** — the room list now sends the backend's `q` search param correctly (`params.search` → `params.q`), and the API client no longer yanks **anonymous** visitors to `/auth` when a public endpoint 401s (the bounce is now reserved for sessions that actually went stale) — regression-tested

---

## 🗺️ Delivery Roadmap

> Tracked like a product backlog — every shipped phase is checked off.

| Phase     | Scope                                                                                                                                                | Status               |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| **1–2**   | React prototype with mock data                                                                                                                       | ✅ Shipped           |
| **2.5**   | Frontend refactor — Vite, TS strict, Tailwind, Zustand, React Query, shadcn/ui                                                                       | ✅ Shipped           |
| **3**     | Django backend — 10+ apps, JWT auth, full REST API, frontend integration                                                                             | ✅ Shipped           |
| **4**     | Real-time chat (Django Channels, typing, read receipts, file upload) + real-time notifications                                                       | ✅ Shipped           |
| **5**     | Payments — SSLCommerz + bKash, refunds, PDF receipts, invoices, security deposits, webhook audit                                                     | ✅ Shipped           |
| **6**     | AI — recommendation engine (content/collaborative/hybrid) + price insight + fair-price prediction                                                    | ✅ Shipped           |
| **Bonus** | Roommate matching (profile + scoring + request flow)                                                                                                 | ✅ Shipped           |
| **Bonus** | Fraud engine (6 detectors, auto-scan, review queue)                                                                                                  | ✅ Shipped           |
| **Bonus** | Paid listing tiers (Free/Featured/Premium monetization)                                                                                              | ✅ Shipped           |
| **Bonus** | Two-factor authentication (email OTP, password-gated enable)                                                                                         | ✅ Shipped           |
| **Bonus** | KYC verification + verified-landlord badge + document upload + audit trail                                                                           | ✅ Shipped           |
| **Bonus** | 2FA recovery codes (10 one-time backups) + email-verified enable                                                                                     | ✅ Shipped           |
| **Bonus** | Passkeys / WebAuthn (passwordless login, conditional UI)                                                                                             | ✅ Shipped           |
| **Bonus** | Geo backend (bbox / radius / landmark queries)                                                                                                       | ✅ Shipped           |
| **7**     | Map (MapLibre GL, clustering, split view, radius + travel overlay, street search, metro routes, room-count API, directions + metro ETA + area chips) | ✅ Shipped           |
| **8**     | Docker Compose + production deployment + HTTPS                                                                                                       | ⏳ Next — CI/CD done |
| **9**     | Reliability & observability — Sentry, JSON logs, Celery + beat, branded emails, audit log, backups, KYC SLA alerts + trend chart                    | ✅ Shipped           |
| **10**    | Growth & personalization — browser push, search v2 (full-text + saved searches), similar-rooms AI, referral program, wishlist sharing, landlord insights, reviews v2 | ✅ Shipped |
| **11**    | Search & Discovery v2 — ✨ AI smart search (Bangla+English NL parser, semantic ranking, visual search), Dhaka expansion                              | ✅ Shipped           |

---

## ✨ Features

**For Tenants**

- Browse and search verified room listings across Dhaka
- AI-powered room recommendations based on budget, area, and preferences
- Advanced filters (area, type, price range, amenities, gender preference)
- Geo search — filter by map viewport (`bbox`), radius around a point, or proximity to landmarks/metro stations
- **Interactive map** (MapLibre GL) — price pins, radius search, university/metro layers, price heatmap
- Wishlist rooms for later
- Book rooms with one click
- Real-time chat with landlords (WebSocket — typing, read receipts, file upload)
- **Roommate matching** — find compatible flatmates by budget, area, lifestyle, and gender preference
- Dashboard with booking stats and notifications

**For Landlords**

- Create and manage room listings with multiple images
- Receive booking requests with approve/reject workflow
- Get notified on new bookings and reviews
- **Fraud protection** — every listing is auto-scanned on creation; flagged listings show an "under review" badge
- **Paid listing tiers** — promote a listing to **Featured** (৳199/30 days) or **Premium** (৳499/30 days) via SSLCommerz/bKash to rank higher in search and show a badge; expired promotions auto-revert to Free
- **KYC verification** — verified landlords carry a trust badge (RoomCard, RoomModal, Roommates, Chat) and rank first; tenants can filter to verified owners only
- Dashboard with revenue stats, ratings, listing analytics, and fraud risk cards with one-click re-scan

**Platform Features**

- JWT authentication (register/login/refresh/logout) with **unique-email enforcement**
- Paid listing tiers (monetization) with server-side pricing and premium-first search ordering
- Real-time notifications (booking updates, reviews, roommate requests, fraud flags)
- Review system with verified stay badges
- 6-detector fraud engine
- Responsive design (mobile, tablet, desktop) + dark mode
- API documentation (Swagger UI + ReDoc)

---

## 🏗️ Tech Stack

### Frontend

| Technology              | Purpose                                    |
| ----------------------- | ------------------------------------------ |
| React 18                | UI framework                               |
| TypeScript (strict)     | Type safety                                |
| Vite                    | Build tool                                 |
| TailwindCSS v4          | Styling                                    |
| shadcn/ui               | Component library                          |
| React Router v6         | Client-side routing                        |
| Zustand                 | Client state management                    |
| TanStack Query          | Server state + caching                     |
| Axios                   | HTTP client with interceptors              |
| React Hook Form + Zod   | Form validation                            |
| Motion                  | Entrance/exit animation                    |
| MapLibre GL JS          | Interactive map (markers, layers, heatmap) |
| zxcvbn-ts               | Password entropy + strength                |
| Pwned Passwords (HIBP)  | k-anonymity breach lookup                  |
| Sonner                  | Toast notifications                        |
| Vitest                  | Unit tests + coverage                      |
| @simplewebauthn/browser | Passkey ceremony client                    |

### Backend

| Technology                    | Purpose                                 |
| ----------------------------- | --------------------------------------- |
| Django 5.2                    | Web framework                           |
| Django REST Framework         | REST API                                |
| Django Channels               | WebSocket support                       |
| Daphne                        | ASGI server                             |
| SimpleJWT                     | JWT authentication                      |
| dj-rest-auth + django-allauth | Auth endpoints                          |
| django-filter                 | API filtering                           |
| drf-spectacular               | OpenAPI docs                            |
| bleach                        | Input sanitization                      |
| difflib                       | Similarity detection (fraud engine)     |
| PostgreSQL 16                 | Production database                     |
| SQLite                        | Development database                    |
| Redis                         | Channel layer + caching + Celery broker |
| Celery                        | Async task queue + beat scheduler       |
| Sentry (sentry-sdk)           | Error tracking (backend + frontend)     |
| py_webauthn                   | WebAuthn/FIDO2 server-side (passkeys)   |
| scikit-learn                  | TF-IDF + LSA semantic search            |
| Pillow (pHash)                | Visual similarity (look-alike rooms)    |
| pywebpush                     | Browser push notifications (VAPID)      |
| pytest / unittest             | Backend tests                           |

---

## 🖥️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend (React SPA)                    │
│  Pages ── hooks (TanStack Query) ── services ── Axios API      │
│  Zustand stores ── WebSocket client ── service worker (push)   │
│  MapLibre GL (map) · WebAuthn (passkeys) · zxcvbn (strength)   │
└───────────────┬──────────────────────────────┬────────────────┘
                │ HTTP /api/v1/*                │ WS /ws/chat/*
┌───────────────▼──────────────────────────────▼────────────────┐
│                    Django (ASGI — Daphne)                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────────────────────┐ │
│  │ JWT Auth   │ │ REST apps  │ │ Channels consumer (chat)   │ │
│  │ 2FA +      │ │ rooms,     │ │ + presence + notifications │ │
│  │ passkeys   │ │ bookings,  │ └────────────────────────────┘ │
│  │ (WebAuthn) │ │ payments,  │ ┌────────────────────────────┐ │
│  └────────────┘ │ roommates, │ │ Fraud engine (6 detectors)│ │
│  ┌────────────┐ │ fraud, AI, │ └────────────────────────────┘ │
│  │ Exception  │ │ saved-     │ ┌────────────────────────────┐ │
│  │ envelope   │ │ searches…  │ │ Semantic search (TF-IDF +  │ │
│  └────────────┘ └────────────┘ │ LSA) · NL parser · pHash   │ │
│  ┌────────────┐                 └────────────────────────────┘ │
│  │ Audit log  │  ┌──────────────────────────────────────────┐ │
│  │ (append-   │  │ Celery + Beat (push, alerts, re-scan)    │ │
│  │ only)      │  └──────────────────────────────────────────┘ │
│  └────────────┘  Sentry (errors) · JSON logs · email templates│
└───────────────┬──────────────────────────────────────────────┘
                │ ORM / cache / channel layer
        ┌───────▼──────────┐   ┌──────────┐   ┌──────────────┐
        │  SQLite (dev) /  │   │  Redis   │   │ SSLCommerz / │
        │  PostgreSQL 16   │   │ (cache,  │   │ bKash gateways│
        └──────────────────┘   │ channel) │   └──────────────┘
                               └──────────┘
```

---

## 📁 Project Structure

```
Rentora/
├── frontend/                  # React SPA
│   ├── src/
│   │   ├── components/        # UI components (Navbar, RoomCard, ChatWindow, PromoteModal, TierBadge…)
│   │   │   └── ui/            # shadcn/ui primitives
│   │   ├── pages/             # Route pages (Home, Rooms, Map, Chat, Dashboard, Roommates, Auth)
│   │   ├── services/          # API service layer (auth, rooms, bookings, roommates, fraud, payments…)
│   │   ├── hooks/             # TanStack Query hooks
│   │   ├── stores/            # Zustand stores (ui, wishlist, notifications)
│   │   ├── context/           # React context (AppContext for auth)
│   │   ├── types/             # TypeScript type definitions
│   │   ├── config/            # Environment config
│   │   └── styles/            # TailwindCSS config + global styles
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── backend/                   # Django REST API
│   ├── config/                # Project config (settings, urls, asgi, exceptions, middleware)
│   │   └── settings/          # Split settings (base, dev, prod)
│   ├── users/                 # Custom User model + auth (unique email enforced)
│   ├── rooms/                 # Room listings + images + geo queries + listing tiers
│   ├── bookings/              # Bookings + Reviews + signals
│   ├── wishlist/              # Wishlist toggle
│   ├── notifications/         # Auto-notifications + API
│   ├── dashboard/             # Aggregated stats endpoint
│   ├── chat/                  # Real-time chat (Channels, WebSocket, presence)
│   ├── payments/              # SSLCommerz + bKash, refunds, invoices, receipts, tier upgrades
│   ├── recommendations/       # Content-based + collaborative + hybrid engine
│   ├── pricing/               # Market stats + price insight + fair-price prediction
│   ├── roommates/             # Roommate profiles + weighted matching algorithm
│   ├── fraud/                 # 6-detector fraud engine + auto-scan + review queue
│   ├── manage.py
│   └── requirements.txt
│
└── docs/                      # Documentation + screenshot tooling
```

---

## 🧪 Quality Engineering

Quality is enforced **in CI and at commit time** — style or coverage drift fails the pipeline automatically.

### Automated tests (414 total)

| Suite             | Count | Gate                                               |
| ----------------- | ----- | -------------------------------------------------- |
| Backend (Django)  | 229   | ✅ passing · coverage ≥ 50% lines (currently ~61%) |
| Frontend (Vitest) | 185   | ✅ passing · coverage ≥ 55% lines (currently ~99%) |

```bash
# Backend
cd backend && venv/Scripts/python.exe -m coverage run manage.py test && venv/Scripts/python.exe -m coverage report

# Frontend
cd frontend && npx vitest run --coverage
```

### Lint & format

```bash
# Backend (ruff)
cd backend
venv/Scripts/python.exe -m ruff check .          # lint
venv/Scripts/python.exe -m ruff check --fix .    # auto-fix
venv/Scripts/python.exe -m ruff format .         # format
venv/Scripts/python.exe -m ruff format --check . # verify

# Frontend (ESLint + Prettier)
cd frontend
npm run lint
npm run format
npm run format:check
```

### Pre-commit hooks (husky + lint-staged)

Installed automatically by `npm install` (`prepare` script). On every commit it runs **only on staged files**:

| Staged file                        | Runs                               |
| ---------------------------------- | ---------------------------------- |
| `backend/**/*.py`                  | `ruff check --fix` + `ruff format` |
| `frontend/**/*.{ts,tsx}`           | `prettier --write` + `eslint`      |
| `frontend/**/*.{css,json,md,html}` | `prettier --write`                 |

If a check fails, the commit is **blocked** — fix and commit again (bypass with `git commit --no-verify` only when intentional).

### CI/CD (GitHub Actions)

| Workflow               | Job                                                         | Runs on         |
| ---------------------- | ----------------------------------------------------------- | --------------- |
| `ci.yml`               | Backend — Django tests + coverage gate                      | every push / PR |
| `ci.yml`               | Frontend — Vitest + coverage + `npm run build`              | every push / PR |
| `ci.yml`               | API contract — boots a server + runs the live endpoint suite vs the docs reference (**status codes + deep JSON schema + OpenAPI path cross-check**, `docs/tools/api-verify.py`) | every push / PR |
| `ci.yml`               | Lint — ruff + ESLint + Prettier                             | every push / PR |
| `coverage-summary.yml` | Posts a coverage **PR comment** (badge + file-level detail) | PRs             |
| `ci.yml` `coverage-history` job | Appends per-branch coverage history (`history-<branch>.csv` + SVG chart) to the `coverage-history` branch | pushes to main **and** PRs (same-repo; fork PRs skip) |

---

## 🚀 Getting Started

### Quick Start (TL;DR)

```bash
git clone https://github.com/SadmaFaahiim/Rentora.git && cd Rentora

# Backend → http://localhost:8000
cd backend
python -m venv venv && venv\Scripts\activate   # (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_rooms                  # 20+ rooms + demo landlords (password: demo12345)
python manage.py runserver

# Frontend → http://localhost:3000 (new terminal)
cd ../frontend
npm install
npm run dev
```

> 💡 `seed_rooms` also creates the demo users below — sign in with any username + `demo12345`.
> No `.env` files are required; sensible defaults work out of the box.

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Seed sample data (rooms + demo landlords)
python manage.py seed_rooms

# Scan all rooms with the fraud engine (optional)
python manage.py scan_rooms

# Create admin user
python manage.py createsuperuser

# Start server
python manage.py runserver

# Backup the database (SQLite copy or pg_dump; prunes old backups)
python ../scripts/backup_db.py --keep 14
```

Backend runs at `http://localhost:8000`

**Celery (optional, async mode)** — with no broker configured, tasks run eagerly
(synchronously) so nothing extra is needed locally. To run a real worker + beat
schedule, start Redis and set `CELERY_BROKER_URL=redis://localhost:6379/0` in
`backend/.env`, then:

```bash
celery -A config worker -l info
celery -A config beat -l info
```

**Error tracking** — set `SENTRY_DSN` (backend `.env`) and `VITE_SENTRY_DSN`
(frontend `.env`) to enable Sentry; leaving them unset keeps everything working
with no events sent. See `docs/ops/backup-restore.md` for the backup/restore
runbook.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env file
echo "VITE_API_BASE_URL=http://localhost:8000/api/v1" > .env

# Start dev server
npm run dev
```

Frontend runs at `http://localhost:3000`

---

## 📡 API Endpoints

### Authentication

| Method | Endpoint                                  | Auth   | Description                                                                                              |
| ------ | ----------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------- |
| POST   | `/api/v1/auth/register/`                  | Public | Register (email must be unique)                                                                          |
| POST   | `/api/v1/auth/login/`                     | Public | Login with email or username (returns JWT)                                                               |
| POST   | `/api/v1/auth/logout/`                    | Auth   | Logout (blacklist token)                                                                                 |
| POST   | `/api/v1/auth/token/refresh/`             | Public | Refresh access token                                                                                     |
| GET    | `/api/v1/auth/user/`                      | Auth   | Get current user profile                                                                                 |
| PATCH  | `/api/v1/auth/user/`                      | Auth   | Update profile                                                                                           |
| POST   | `/api/v1/auth/otp/verify/`                | Public | Finish 2FA login: exchange (challenge, code) for JWTs; pass `recovery_code` instead to use a backup code |
| POST   | `/api/v1/auth/otp/resend/`                | Public | Re-send the one-time code (cooldown-guarded)                                                             |
| POST   | `/api/v1/auth/otp/toggle/`                | Auth   | Disable 2FA, or begin enabling (password → emailed code)                                                 |
| POST   | `/api/v1/auth/otp/confirm-enable/`        | Auth   | Confirm the emailed code → 2FA on + one-time recovery codes                                              |
| POST   | `/api/v1/auth/passkey/register/begin/`    | Auth   | Registration options for the browser ceremony                                                            |
| POST   | `/api/v1/auth/passkey/register/complete/` | Auth   | Verify + store the new passkey (public key only)                                                         |
| POST   | `/api/v1/auth/passkey/login/begin/`       | Public | Authentication options + `challenge_id` (conditional UI)                                                 |
| POST   | `/api/v1/auth/passkey/login/complete/`    | Public | Verify the assertion → JWTs (or pending OTP for 2FA)                                                     |

### Rooms

| Method    | Endpoint                   | Auth   | Description                                       |
| --------- | -------------------------- | ------ | ------------------------------------------------- |
| GET       | `/api/v1/rooms/`           | Public | List rooms (filter/search/sort/geo/tier ordering) |
| GET       | `/api/v1/rooms/:id/`       | Public | Room detail                                       |
| POST      | `/api/v1/rooms/`           | Auth   | Create listing                                    |
| PUT/PATCH | `/api/v1/rooms/:id/`       | Owner  | Update listing                                    |
| DELETE    | `/api/v1/rooms/:id/`       | Owner  | Delete listing                                    |
| GET       | `/api/v1/rooms/landmarks/` | Public | List landmarks (for `near_landmark`)              |
| GET       | `/api/v1/rooms/summary/`   | Public | COUNT/AVG for the current viewport (map badge)    |
| GET       | `/api/v1/rooms/geocode/?q=` | Public | Geocode a street/area (gazetteer + Nominatim)    |
| GET       | `/api/v1/rooms/insights/`  | Auth (own listings) | Per-listing engagement + price vs area stats      |
| POST      | `/api/v1/rooms/bulk/`      | Auth  | Bulk-create listings (JSON array body)            |
| GET       | `/api/v1/rooms/tier-catalog/` | Public | Tier pricing + benefits (drives Promote UI)     |
| GET       | `/api/v1/rooms/:id/similar-images/` | Public | Rooms whose primary photo looks like this one (pHash) |

**Text filters:** `?area=Dhanmondi&room_type=studio&price__gte=5000&price__lte=15000&is_available=true&q=cozy&ordering=-price&owner=3`

**Smart search:** `?q=১০ হাজার এর মধ্যে uttara student room&smart=1` — natural-language parsing (budget/area/type/gender become filters), semantic ranking over the filtered pool, and an `nl_parsed` block in the response describing what was understood.

**Geo filters:**

- `bbox=min_lng,min_lat,max_lng,max_lat` — map viewport (leaflet `getBounds()`)
- `near_lat=23.75&near_lng=90.39&radius_km=2` — radius around a point (nearest-first)
- `near_landmark=mirpur-10-metro&radius_km=3` — radius around a named landmark/metro station

### Bookings

| Method | Endpoint                | Auth | Description                     |
| ------ | ----------------------- | ---- | ------------------------------- |
| GET    | `/api/v1/bookings/`     | Auth | My bookings (tenant + landlord) |
| POST   | `/api/v1/bookings/`     | Auth | Create booking request          |
| PATCH  | `/api/v1/bookings/:id/` | Auth | Update status (role-gated)      |

### Reviews

| Method | Endpoint                    | Auth   | Description                               |
| ------ | --------------------------- | ------ | ----------------------------------------- |
| GET    | `/api/v1/reviews/?room=:id` | Public | Reviews for a room                        |
| POST   | `/api/v1/reviews/`          | Auth   | Create review (requires approved booking) |
| GET    | `/api/v1/reviews/summary/?room=:id` | Public | Rating breakdown (5★ histogram + avg + verified badges) |

### Wishlist

| Method | Endpoint                   | Auth | Description                  |
| ------ | -------------------------- | ---- | ---------------------------- |
| GET    | `/api/v1/wishlist/`        | Auth | My wishlisted rooms          |
| POST   | `/api/v1/wishlist/toggle/` | Auth | Toggle wishlist (`room_id` body) |
| GET    | `/api/v1/wishlist/share-info/` | Auth | Get my public share token + link |
| GET    | `/api/v1/wishlist/share/:token/` | Public | Public read-only wishlist (no personal info, 404 on bad token) |

### Notifications

| Method | Endpoint                               | Auth | Description      |
| ------ | -------------------------------------- | ---- | ---------------- |
| GET    | `/api/v1/notifications/`               | Auth | My notifications |
| PATCH  | `/api/v1/notifications/:id/`           | Auth | Mark as read     |
| POST   | `/api/v1/notifications/mark-all-read/` | Auth | Mark all read    |
| GET    | `/api/v1/notifications/unread-count/`  | Auth | Unread count     |
| POST   | `/api/v1/notifications/push/subscribe/` | Auth | Register a browser push subscription (VAPID) |

### Saved Searches

| Method   | Endpoint                     | Auth | Description                          |
| -------- | ---------------------------- | ---- | ------------------------------------ |
| GET      | `/api/v1/saved-searches/`    | Auth | My saved searches                    |
| POST     | `/api/v1/saved-searches/`    | Auth | Save the current filter set          |
| DELETE   | `/api/v1/saved-searches/:id/` | Auth | Delete a saved search                |
| POST     | `/api/v1/saved-searches/:id/check/` | Auth | Manual "check now" for new matches |

> A daily Celery beat task (`check_saved_searches`) notifies you when a **new** matching listing appears.

### Users / Referral

| Method | Endpoint              | Auth | Description                          |
| ------ | --------------------- | ---- | ------------------------------------ |
| GET    | `/api/v1/users/referral/` | Auth | My referral code, invite link + who joined |

### Dashboard

| Method | Endpoint                   | Auth | Description                    |
| ------ | -------------------------- | ---- | ------------------------------ |
| GET    | `/api/v1/dashboard/stats/` | Auth | User stats (tenant + landlord) |

### Chat

| Method   | Endpoint                           | Auth | Description                                   |
| -------- | ---------------------------------- | ---- | --------------------------------------------- |
| GET/POST | `/api/v1/chat/rooms/`              | Auth | List / create chat rooms                      |
| GET      | `/api/v1/chat/rooms/:id/messages/` | Auth | Messages in a room                            |
| POST     | `/api/v1/chat/rooms/:id/messages/` | Auth | Send a message                                |
| GET      | `/api/v1/chat/online-status/`      | Auth | Online status of users                        |
| POST     | `/api/v1/chat/upload/`             | Auth | Upload a chat attachment                      |
| WS       | `/ws/chat/:room_id/`               | Auth | Real-time chat socket (typing, read receipts) |

### Payments

| Method | Endpoint                                             | Auth   | Description                     |
| ------ | ---------------------------------------------------- | ------ | ------------------------------- |
| POST   | `/api/v1/payments/initiate/`                         | Auth   | Initiate a payment (SSLCommerz) |
| POST   | `/api/v1/payments/bkash/initiate/`                   | Auth   | Initiate a bKash payment        |
| POST   | `/api/v1/payments/bkash/callback/`                   | Public | bKash gateway callback          |
| POST   | `/api/v1/payments/sslcommerz/success\|fail\|cancel/` | Public | SSLCommerz callbacks            |
| GET    | `/api/v1/payments/`                                  | Auth   | My payment history              |
| GET    | `/api/v1/payments/:id/`                              | Auth   | Payment detail / receipt        |
| POST   | `/api/v1/payments/:id/refund/`                       | Auth   | Request a refund                |
| GET    | `/api/v1/payments/summary/`                          | Auth   | Payment summary                 |

### Recommendations

| Method | Endpoint                           | Auth | Description                 |
| ------ | ---------------------------------- | ---- | --------------------------- |
| GET    | `/api/v1/recommendations/?limit=N` | Auth | Hybrid room recommendations |
| GET    | `/api/v1/recommendations/similar/:id/` | Public | Content-based similar rooms (modal carousel, match % + reasons) |

### Pricing (AI)

| Method | Endpoint                                           | Auth   | Description                          |
| ------ | -------------------------------------------------- | ------ | ------------------------------------ |
| POST   | `/api/v1/pricing/predict/`                         | Auth   | Predict fair price for a new listing |
| GET    | `/api/v1/pricing/insight/:room_id/`                | Public | Price insight vs market for a room   |
| GET    | `/api/v1/pricing/market-stats/?area=X&room_type=Y` | Public | Raw market stats                     |

### Roommates

| Method   | Endpoint                                 | Auth     | Description                                  |
| -------- | ---------------------------------------- | -------- | -------------------------------------------- |
| GET/PUT  | `/api/v1/roommates/profile/`             | Auth     | Get / upsert my roommate profile             |
| GET      | `/api/v1/roommates/matches/`             | Auth     | Best-first scored match suggestions          |
| GET/POST | `/api/v1/roommates/requests/`            | Auth     | My requests (incoming + outgoing) / send one |
| POST     | `/api/v1/roommates/requests/:id/action/` | Receiver | Approve or reject a request                  |

### Fraud Detection

| Method | Endpoint                                   | Auth        | Description                                                            |
| ------ | ------------------------------------------ | ----------- | ---------------------------------------------------------------------- |
| GET    | `/api/v1/fraud/rooms/:room_id/status/`     | Public      | Public badge data (drives "under review" badge)                        |
| GET    | `/api/v1/fraud/reports/`                   | Auth        | Reports (owner: own rooms; admin: all) — filter by `status`/`severity` |
| POST   | `/api/v1/fraud/rooms/:room_id/scan/`       | Owner/Admin | Re-run the detector on a room                                          |
| POST   | `/api/v1/fraud/reports/:report_id/review/` | Admin       | Mark reviewed / dismissed                                              |

### Listing Tiers (Monetization)

| Method | Endpoint                                  | Auth   | Description                                                      |
| ------ | ----------------------------------------- | ------ | ---------------------------------------------------------------- |
| GET    | `/api/v1/rooms/tier-catalog/`             | Public | Tier pricing + benefits catalog (drives the Promote UI)          |
| POST   | `/api/v1/payments/tier-upgrade/initiate/` | Owner  | Start a promotion payment (Featured/Premium; amount server-side) |

Tiers: **Free** (default) → **Featured** (৳199/30d: boosted above free, badge, Home "Featured Rooms") → **Premium** (৳499/30d: top of search, gold badge, priority in AI recommendations). Expired promotions revert to Free automatically (`expire_listings` management command + query-time `effective_tier`).

### KYC Verification

| Method | Endpoint                                                      | Auth        | Description                                                          |
| ------ | ------------------------------------------------------------- | ----------- | -------------------------------------------------------------------- |
| GET    | `/api/v1/users/kyc/documents/`                                | Auth        | My KYC documents (admin: all)                                        |
| POST   | `/api/v1/users/kyc/documents/`                                | Auth        | Upload a NID/passport document (multipart, 5 MB cap)                 |
| GET    | `/api/v1/users/kyc/documents/:id/file/`                       | Owner/Admin | **Auth-gated document file** — strangers get 404 (no existence leak) |
| GET    | `/api/v1/users/kyc/pending/`                                  | Admin       | Pending applications queue                                           |
| POST   | `/api/v1/users/kyc/:user_id/review/`                          | Admin       | Approve/reject (badge sync + audit log + notification, atomic)       |
| GET    | `/api/v1/users/kyc/audit/`                                    | Admin       | Full KYC decision trail (who/when/note from the audit log)           |
| GET    | `/api/v1/users/kyc/sla/`                                      | Admin       | Review-queue health: pending count, avg review hours, 7-day trend, **breach flags** (`oldest_pending` / `trend_negative`) and 30-day daily trend (`trend_30d`) |
| GET    | `/api/v1/rooms/?verified=true`                                | Public      | Only rooms owned by KYC-approved landlords                           |

### Documentation

| Endpoint          | Description           |
| ----------------- | --------------------- |
| `/api/v1/docs/`   | Swagger UI            |
| `/api/v1/redoc/`  | ReDoc                 |
| `/api/v1/schema/` | OpenAPI schema (YAML) |

> 📖 Deeper reading: [`docs/architecture.md`](docs/architecture.md) (system design, data model, flows, deployment) · [`docs/api-reference.md`](docs/api-reference.md) (full endpoint reference + curl examples) · [`docs/ops/backup-restore.md`](docs/ops/backup-restore.md) (backup/restore runbook)

---

## 🔐 Security

- JWT authentication with access/refresh token rotation
- **Unique email enforced at the API and database layers** (registration, admin, seed scripts all covered)
- Rate limiting (auth: 10/hr per IP, anon: 100/hr, user: 1000/hr, payment initiation: 5/hr)
- Input sanitization via bleach on all user-generated text
- CORS configured (dev: all origins, prod: pinned domains)
- Custom error handler with consistent JSON envelope
- Production security headers (HSTS, XSS filter, content-type nosniff)
- **Append-only audit log** for sensitive actions (fraud-report reviews, 2FA changes) — immutable in the admin, so an audit trail cannot be rewritten
- **Error tracking** via Sentry (backend + frontend) and **structured JSON logs** (`JSON_LOGS=True`) so incidents are visible and searchable
- **Defensive fraud scanning** — a detector or queue failure can never break room creation; detector errors are isolated and logged
- **Fraud engine** auto-scans every new listing — flagged listings go into an admin review queue
- **Password hygiene on register** — zxcvbn-ts entropy scoring rejects trivially guessable passwords with actionable warnings; HaveIBeenPwned k-anonymity check warns when the chosen password appears in known data breaches (nothing but a 5-char hash prefix ever leaves the device)
- **Two-factor authentication (email OTP)** — challenge codes are stored hashed, TTL-bounded (10 min), attempt-limited (5 → lock) and cooldown-guarded; the login endpoint never returns tokens for a 2FA account until the code is verified
- **2FA enable is email-verified** — password + emailed code are both required before `otp_enabled` flips, and **recovery codes** (10, hashed, single-use) are minted at that moment; disabling deletes them
- **Passkeys** — public-key only storage, sign-counter replay protection, conditional UI on login
- **KYC document privacy** — identity documents are served through an **auth-gated endpoint** (owner/admin only); the public media URL can never expose a document, and non-owners get a 404 so even file existence is hidden

## 🔑 Passkeys / WebAuthn — Shipped

Passwordless sign-in is live — the phishing-resistant successor to passwords + OTP:

| Aspect              | TOTP/OTP (email)                                | Passkeys (WebAuthn)                             |
| ------------------- | ----------------------------------------------- | ----------------------------------------------- |
| UX friction         | Open email, copy 6-digit code                   | One tap / biometric (Touch ID, Windows Hello)   |
| Phishing resistance | Vulnerable (codes can be typed into fake sites) | **Immune** — bound to the exact origin (`rpId`) |
| Secrets             | Shared secret stored server-side                | Server stores **public keys only**              |

**Implemented with** `py_webauthn` (webauthn 3.x, Duo Labs) server-side + `@simplewebauthn/browser` client-side. Four DRF endpoints: `passkey/register/begin` → `passkey/register/complete` (JWT-authed), `passkey/login/begin` → `passkey/login/complete` (issues JWTs). Conditional UI (`mediation: 'conditional'`) surfaces passkeys in the browser's native autofill; a manual **"Sign in with a passkey"** button is the fallback. Register/revoke from Dashboard → Security → Passkeys.

**Gotchas handled:** WebAuthn requires a secure origin (`localhost` is fine; IP addresses are not); frontend/backend should share a registrable domain in production (e.g. `app.example.com` + `api.example.com` with `rpId: example.com`); an `AbortController` cancels a pending conditional ceremony when the user submits the password form.

---

## 🧑‍💻 Demo Users

> Seed the database first (see [Getting Started](#-getting-started)), then sign in with any of these accounts. Password for all: **`demo12345`**

| Role        | Username        | What to explore                                                                                         |
| ----------- | --------------- | ------------------------------------------------------------------------------------------------------- |
| 🏠 Landlord | `rahim.hossain` | Roommate matches (Sabbir 87%, Nadia 76%), room listing, **Paid Tiers** (Dashboard → Listings → Promote) |
| 🏠 Landlord | `nadia.islam`   | Shared Premium Gulshan listing                                                                          |
| 🏠 Landlord | `sabbir.rahman` | Student Room Azimpur listing                                                                            |
| 🏠 Landlord | `farhana.akter` | Modern Studio Mirpur listing                                                                            |
| 🏠 Landlord | `tanvir.islam`  | Fraud dashboard (Executive Single Banani + re-scan)                                                     |
| 🏠 Landlord | `demo.promoter` | **Fresh FREE listing** — try the Promote flow end-to-end                                                |
| 🏠 Landlord | `kyc.demo`      | **Unverified landlord** — Dashboard → KYC: upload a document, then watch an admin approve it and the **verified badge** appear on your listing + chat                                      |
| 🏠 Landlord | `kyc.rejected`  | **Rejected KYC demo** — Dashboard → KYC shows the **"Why it was rejected"** banner with the reviewer's note and a ready re-upload form                                  |

**Tips**

- All seeded accounts are **landlords** — to explore the **tenant** side (browse, search, wishlist, book, chat), just **register a fresh account** from the login page (unique email required) or use the platform anonymously for browsing.
- **Admin:** run `python manage.py createsuperuser` then open `http://localhost:8000/admin/` — the fraud review queue, KYC review, and the append-only audit trail live there.
- Sign in with the **username** (e.g. `rahim.hossain`) **or** the email address (e.g. `rahim.hossain@rentora.com`) — both work.
- `rahim.hossain` has a roommate profile — log in and open **Roommates** to see live match scores.
- `tanvir.islam` has listings — open **Dashboard → Fraud** to see the risk cards and try **Re-scan**.
- `kyc.rejected` starts with a rejected document — open **Dashboard → KYC** to see the rejection note, then upload a clear copy to restart the review loop.
- **Try 2FA:** Dashboard → **Two-Factor Authentication** → **Enable 2FA** (current password → emailed code → save your **recovery codes**). Next sign-in asks for the emailed code (or a recovery code). In development the code prints to the backend console; in production it goes to the account's email.
- **Try passkeys:** Dashboard → Security → **Passkeys** → **Register a passkey** (your device's biometric/PIN), then sign out and use the login page's passkey autofill or the **"Sign in with a passkey"** button.

> 💡 Screenshots can be regenerated with [`docs/tools/capture-screenshots.mjs`](docs/tools/capture-screenshots.mjs) — it drives headless Chrome, mints demo tokens via Django, and saves fresh PNGs into `docs/screenshots/`.

---

## 🖼️ Screenshots

**Interactive Map (MapLibre GL)** — street-search autocomplete, price marker pins, clustering, split-view list, radius search, walking travel-time overlay & MRT Line 6 corridor:

<img width="1440" alt="Interactive Map" src="docs/screenshots/map-view.png" />

**Interactive Map — dark theme** (auto fallback to dimmed OSM tiles keeps the map readable):

<img width="1440" alt="Interactive Map Dark" src="docs/screenshots/map-view-dark.png" />

**Roommate Matching** — find compatible flatmates by budget, area, lifestyle & gender preference:

<img width="1440" alt="Roommate Matching" src="docs/screenshots/roommates-matching.png" />

**Fraud Detection** — auto-scanned listings with risk scores & one-click re-scan from the landlord dashboard:

<img width="1440" alt="Fraud Detection Dashboard" src="docs/screenshots/fraud-detection.png" />

**Login / Register** — animated Dribbble-style auth dialog (live password strength meter in register mode):

<img width="1440" alt="Auth Login" src="docs/screenshots/auth-login.png" />

**Two-step verification (email OTP)** — password-first login pauses at a verification-code step; tokens are issued only after the code checks out:

<img width="1440" alt="OTP Verification" src="docs/screenshots/otp-verification.png" />

**KYC Verification** — upload identity documents from the landlord dashboard, review pending applications as admin, and see the decision trail (audit log):

<img width="1440" alt="KYC Upload" src="docs/screenshots/kyc-upload.png" />

<img width="1440" alt="KYC Admin Panel" src="docs/screenshots/kyc-admin-panel.png" />

**KYC Review SLA Stats** — the admin panel's queue-health strip (pending volume, average review time, 7-day decision trend) with red **breach badges** when the queue slips past 48h or trails last week:

<img width="1440" alt="KYC SLA Stats" src="docs/screenshots/kyc-sla.png" />

**KYC 30-day decision trend** — the History view's SVG chart: bars are decisions per day, the line is average review time, so the review team can see capacity at a glance:

<img width="1440" alt="KYC Trend Chart" src="docs/screenshots/kyc-trend-chart.png" />

**Phase 10 — Dashboard growth cards** — the referral invite card (copy link + WhatsApp/Facebook) and the browser push-notification toggle on the Dashboard overview:

<img width="1440" alt="Phase 10 Dashboard Growth" src="docs/screenshots/phase10-dashboard-growth.png" />

**Phase 10 — Landlord Insights** — per-listing views (7d/30d), wishlist saves, bookings and price vs area-average positioning:

<img width="1440" alt="Phase 10 Landlord Insights" src="docs/screenshots/phase10-insights.png" />

**Phase 10 — Saved Searches** — save the current search from the Rooms page and get alerted about new matching listings:

<img width="1440" alt="Phase 10 Saved Search" src="docs/screenshots/phase10-saved-search.png" />

**Phase 11 — AI Smart Search** — the ✨ AI Search toggle turns the search box into a natural-language query box: "দশ হাজার এর মধ্যে উত্তরা" (Bangla number *words* + Bangla area names) is understood as **budget ≤ ৳10,000 in Uttara** (see the "AI understood" chips under the bar) and ranked semantically — no keyword matching needed:

<img width="1440" alt="Phase 11 AI Smart Search" src="docs/screenshots/phase11-ai-search.png" />

**Verified badge — dark theme** (the ✓ Verified pill stays legible in dark mode):

<img width="1440" alt="Verified Badge Dark" src="docs/screenshots/verified-badge-dark.png" />

**KYC on mobile** — the identity card + verified state on a phone-sized screen:

<img width="390" alt="KYC Mobile" src="docs/screenshots/kyc-mobile.png" />

**Home & Listing Pages:**

<img width="1920" height="2178" alt="RentRoom_BD" src="https://github.com/user-attachments/assets/8e7cd2b5-174e-4855-a8d6-beea394a12cc" />
<img width="1920" height="1433" alt="RentRoom_BD__1_" src="https://github.com/user-attachments/assets/e03dcd15-632b-4e2d-8659-de4bc2946f43" />
<img width="1920" height="927" alt="RentRoom_BD__3_" src="https://github.com/user-attachments/assets/6dc84e24-8d02-4cf5-a6a6-3ff926b21371" />
<img width="1920" height="927" alt="RentRoom_BD__2_" src="https://github.com/user-attachments/assets/6b958b77-127f-4424-8b62-76b6f6a09520" />

---

## 🔄 Team Workflow

- **Branching:** feature work happens on `feature/<name>` branches off `main`; never commit directly to `main`.
- **Pull requests:** every branch ships as a PR against `main`; CI must be green (tests, coverage, lint, build) before merge.
- **Pre-commit:** husky + lint-staged format and lint staged files on every commit.
- **Environments:** local dev (SQLite + runserver) → CI (GitHub Actions) → production (PostgreSQL + Daphne, Phase 8).

---

## 👨‍💻 Developer

**Sadman Chowdhury Fahim**

- GitHub: [@SadManFahIm](https://github.com/SadManFahIm)

---

## 📄 License

This project is licensed under the MIT License.
