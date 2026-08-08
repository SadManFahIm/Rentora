# 🏠 Rentora — AI-Powered Room Rental Platform

> Bangladesh's smartest room rental platform. Find verified, affordable rooms with AI-powered recommendations, real-time chat, secure payments, roommate matching, and fraud detection.

[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6?logo=typescript)](https://typescriptlang.org)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![DRF](https://img.shields.io/badge/DRF-3.15-a30000?logo=django)](https://www.django-rest-framework.org/)
[![Tests](<https://img.shields.io/badge/tests-246%20(122%20BE%20%2B%20124%20FE)-success>)](https://github.com/SadmaFaahiim/Rentora/actions)
[![Coverage](https://img.shields.io/badge/coverage-BE%2060%25%20%E2%80%A2%20FE%2099%25-success)](https://github.com/SadmaFaahiim/Rentora/actions)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions)](https://github.com/SadmaFaahiim/Rentora/actions)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📋 Product Overview

|                     |                                                                                                                                                                                               |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Problem**         | Finding a trustworthy room in Dhaka is hard — listings are scattered, landlords are hard to verify, and scams are common.                                                                     |
| **Solution**        | One verified marketplace: AI-scanned listings, real-time landlord chat, secure gateway payments, roommate matching, and an ML-powered fraud engine that catches bad actors before tenants do. |
| **Target users**    | Tenants (students & young professionals) and landlords in Bangladesh.                                                                                                                         |
| **Differentiators** | Fraud-engineered trust layer, AI recommendations & fair-price insight, roommates (a growth hook competitors lack), and a monetized listing-tier system (Free → Featured → Premium).           |

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
- **Marker clustering** — with many listings in view, pins collapse into numbered cluster circles (click one to zoom in); toggle between **Clustered** and **Pins** modes
- **Viewport sync** — panning/zooming refetches rooms inside the visible `bbox` (debounced 300ms), so the map and the room count always match what's on screen
- **Radius search** — click a point on the map (or a university chip) and drag a slider to see rooms within 0.5–5 km, powered by the geo backend's `near_lat`/`near_lng` + `radius_km`
- **Travel-time overlay** — with a search point active, toggle **Travel** to draw walking isochrones (10/20/30 min bands, green → amber → red) so tenants see how far they can get on foot from a university, metro or office
- **Distance markers** — every listing in a radius search shows `formatDistance` + walking time ("1.2 km away · ≈ 16 min walk") in its map popup and the side list, from the backend's `distance_km` annotation
- **Viewport bbox cache** — the refetch bbox is quantized to ~100 m, so micro-pans hit the React Query cache instead of firing duplicate API calls
- **Landmark layers** — toggle universities 🎓 and metro stations 🚇 on/off as map layers (from `/rooms/landmarks/`)
- **Price heatmap** — green → amber → red circles scaled by rent, so expensive areas are visible at a glance
- **Map + list split view** — a viewport-synced sidebar lists the rooms on screen (promoted first, then by price); on mobile it becomes a bottom sheet
- Tapping a pin opens the room popup → full **RoomModal** (booking, chat, fraud badge, AI price insight)
- **Readable in both themes** — dark tiles are the CARTO CDN; if it's unreachable the map auto-falls back to dimmed OSM tiles (street labels stay legible), and the travel overlay + legend are styled for light *and* dark

**Listing Location Picker (landlord)**

- **List a Room** now opens a proper form with a **map picker** — click the map to pin the exact listing location (or "Use my location")
- Coordinates are stored as `lat`/`lng`, powering the map view, geo search and price insight

**Engineering**

- **Coverage history per branch** — every PR and main push appends its own `history-<branch>.csv` + SVG chart to the `coverage-history` branch (viewable `index.html` linking all branches)
- 246 automated tests (122 backend + 124 frontend) · coverage gates (BE ≥50%, FE ≥55%)
- Ruff + ESLint + Prettier with husky/lint-staged pre-commit hooks
- GitHub Actions CI (backend, frontend, lint, coverage-summary PR comment, per-branch coverage history)
- Route-level code splitting (React.lazy) — smaller bundles

---

## 🗺️ Delivery Roadmap

> Tracked like a product backlog — every shipped phase is checked off.

| Phase     | Scope                                                                                             | Status               |
| --------- | ------------------------------------------------------------------------------------------------- | -------------------- |
| **1–2**   | React prototype with mock data                                                                    | ✅ Shipped           |
| **2.5**   | Frontend refactor — Vite, TS strict, Tailwind, Zustand, React Query, shadcn/ui                    | ✅ Shipped           |
| **3**     | Django backend — 10+ apps, JWT auth, full REST API, frontend integration                          | ✅ Shipped           |
| **4**     | Real-time chat (Django Channels, typing, read receipts, file upload) + real-time notifications    | ✅ Shipped           |
| **5**     | Payments — SSLCommerz + bKash, refunds, PDF receipts, invoices, security deposits, webhook audit  | ✅ Shipped           |
| **6**     | AI — recommendation engine (content/collaborative/hybrid) + price insight + fair-price prediction | ✅ Shipped           |
| **Bonus** | Roommate matching (profile + scoring + request flow)                                              | ✅ Shipped           |
| **Bonus** | Fraud engine (6 detectors, auto-scan, review queue)                                               | ✅ Shipped           |
| **Bonus** | Paid listing tiers (Free/Featured/Premium monetization)                                           | ✅ Shipped           |     | **Bonus** | Two-factor authentication (email OTP, password-gated enable) | ✅ Shipped |
| **Bonus** | 2FA recovery codes (10 one-time backups) + email-verified enable                                  | ✅ Shipped           |
| **Bonus** | Passkeys / WebAuthn (passwordless login, conditional UI)                                          | ✅ Shipped           |
| **Bonus** | Geo backend (bbox / radius / landmark queries)                                                    | ✅ Shipped           |
| **7**     | Map frontend (MapLibre GL, price heatmap, university/metro layers, radius search)                 | ✅ Shipped           |
| **8**     | Docker Compose + production deployment + HTTPS                                                    | ⏳ Next — CI/CD done |

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
| Vitest                  | Unit tests + coverage                      |     | SHA-256 OTP challenge | Email 2FA (hashed codes) |
| py_webauthn             | WebAuthn/FIDO2 server-side                 |
| @simplewebauthn/browser | Passkey ceremony client                    |

### Backend

| Technology                    | Purpose                             |
| ----------------------------- | ----------------------------------- |
| Django 5.2                    | Web framework                       |
| Django REST Framework         | REST API                            |
| Django Channels               | WebSocket support                   |
| Daphne                        | ASGI server                         |
| SimpleJWT                     | JWT authentication                  |
| dj-rest-auth + django-allauth | Auth endpoints                      |
| django-filter                 | API filtering                       |
| drf-spectacular               | OpenAPI docs                        |
| bleach                        | Input sanitization                  |
| difflib                       | Similarity detection (fraud engine) |
| PostgreSQL 16                 | Production database                 |
| SQLite                        | Development database                |
| Redis                         | Channel layer + caching             |
| pytest / unittest             | Backend tests                       |

---

## 🖥️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend (React SPA)                    │
│  Pages ── hooks (TanStack Query) ── services ── Axios API      │
│  Zustand stores (wishlist/notifications) ── WebSocket client   │
└───────────────┬──────────────────────────────┬────────────────┘
                │ HTTP /api/v1/*                │ WS /ws/chat/*
┌───────────────▼──────────────────────────────▼────────────────┐
│                    Django (ASGI — Daphne)                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────────────────────┐ │
│  │ JWT Auth   │ │ REST apps  │ │ Channels consumer (chat)   │ │
│  │ dj-rest-   │ │ rooms,     │ │ + presence + notifications │ │
│  │ auth +     │ │ bookings,  │ └────────────────────────────┘ │
│  │ allauth    │ │ payments,  │ ┌────────────────────────────┐ │
│  └────────────┘ │ roommates, │ │ Fraud engine (6 detectors)│ │
│  ┌────────────┐ │ fraud, AI  │ └────────────────────────────┘ │
│  │ Exception  │ │ pricing…   │ ┌────────────────────────────┐ │
│  │ envelope   │ └────────────┘ │ Recommendations engine     │ │
│  └────────────┘                 └────────────────────────────┘ │
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

### Automated tests (246 total)

| Suite             | Count | Gate                                               |
| ----------------- | ----- | -------------------------------------------------- |
| Backend (Django)  | 122   | ✅ passing · coverage ≥ 50% lines (currently ~61%) |
| Frontend (Vitest) | 116   | ✅ passing · coverage ≥ 55% lines (currently ~99%) |

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
| `ci.yml`               | Lint — ruff + ESLint + Prettier                             | every push / PR |
| `coverage-summary.yml` | Posts a coverage **PR comment** (badge + file-level detail) | PRs             |     | `ci.yml` `coverage-history` job | Appends per-branch coverage history (`history-<branch>.csv` + SVG chart) to the `coverage-history` branch | pushes to main **and** PRs (same-repo; fork PRs skip) |

---

## 🚀 Getting Started

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
```

Backend runs at `http://localhost:8000`

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

**Text filters:** `?area=Dhanmondi&room_type=studio&price__gte=5000&price__lte=15000&is_available=true&search=cozy&ordering=-price&owner=3`

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

### Wishlist

| Method | Endpoint                   | Auth | Description                  |
| ------ | -------------------------- | ---- | ---------------------------- |
| GET    | `/api/v1/wishlist/`        | Auth | My wishlisted rooms          |
| POST   | `/api/v1/wishlist/toggle/` | Auth | Toggle wishlist (add/remove) |

### Notifications

| Method | Endpoint                               | Auth | Description      |
| ------ | -------------------------------------- | ---- | ---------------- |
| GET    | `/api/v1/notifications/`               | Auth | My notifications |
| PATCH  | `/api/v1/notifications/:id/`           | Auth | Mark as read     |
| POST   | `/api/v1/notifications/mark-all-read/` | Auth | Mark all read    |
| GET    | `/api/v1/notifications/unread-count/`  | Auth | Unread count     |

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

### Documentation

| Endpoint          | Description           |
| ----------------- | --------------------- |
| `/api/v1/docs/`   | Swagger UI            |
| `/api/v1/redoc/`  | ReDoc                 |
| `/api/v1/schema/` | OpenAPI schema (YAML) |

---

## 🔐 Security

- JWT authentication with access/refresh token rotation
- **Unique email enforced at the API and database layers** (registration, admin, seed scripts all covered)
- Rate limiting (auth: 10/hr per IP, anon: 100/hr, user: 1000/hr, payment initiation: 5/hr)
- Input sanitization via bleach on all user-generated text
- CORS configured (dev: all origins, prod: pinned domains)
- Custom error handler with consistent JSON envelope
- Production security headers (HSTS, XSS filter, content-type nosniff)
- **Fraud engine** auto-scans every new listing — flagged listings go into an admin review queue
- **Password hygiene on register** — zxcvbn-ts entropy scoring rejects trivially guessable passwords with actionable warnings; HaveIBeenPwned k-anonymity check warns when the chosen password appears in known data breaches (nothing but a 5-char hash prefix ever leaves the device)
- **Two-factor authentication (email OTP)** — challenge codes are stored hashed, TTL-bounded (10 min), attempt-limited (5 → lock) and cooldown-guarded; the login endpoint never returns tokens for a 2FA account until the code is verified
- **2FA enable is email-verified** — password + emailed code are both required before `otp_enabled` flips, and **recovery codes** (10, hashed, single-use) are minted at that moment; disabling deletes them
- **Passkeys** — public-key only storage, sign-counter replay protection, conditional UI on login

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

**Tips**

- Sign in with the **username** (e.g. `rahim.hossain`) **or** the email address (e.g. `rahim.hossain@rentora.com`) — both work.
- `rahim.hossain` has a roommate profile — log in and open **Roommates** to see live match scores.
- `tanvir.islam` has listings — open **Dashboard → Fraud** to see the risk cards and try **Re-scan**.
- **Try 2FA:** Dashboard → **Two-Factor Authentication** → **Enable 2FA** (current password → emailed code → save your **recovery codes**). Next sign-in asks for the emailed code (or a recovery code). In development the code prints to the backend console; in production it goes to the account's email.
- **Try passkeys:** Dashboard → Security → **Passkeys** → **Register a passkey** (your device's biometric/PIN), then sign out and use the login page's passkey autofill or the **"Sign in with a passkey"** button.

> 💡 Screenshots can be regenerated with [`docs/tools/capture-screenshots.mjs`](docs/tools/capture-screenshots.mjs) — it drives headless Chrome, mints demo tokens via Django, and saves fresh PNGs into `docs/screenshots/`.

---

## 🖼️ Screenshots

**Interactive Map (MapLibre GL)** — price marker pins, clustering, split-view list, radius search & walking travel-time overlay:

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
