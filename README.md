# 🏠 Rentora — AI-Powered Room Rental Platform

> Bangladesh's smartest room rental platform. Find verified, affordable rooms with AI-powered recommendations, real-time chat, secure payments, roommate matching, and fraud detection.

[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6?logo=typescript)](https://typescriptlang.org)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![DRF](https://img.shields.io/badge/DRF-3.15-a30000?logo=django)](https://www.django-rest-framework.org/)
[![Tests](<https://img.shields.io/badge/tests-170%20(98%20BE%20%2B%2072%20FE)-success>)](https://github.com/SadmaFaahiim/Rentora/actions)
[![Coverage](https://img.shields.io/badge/coverage-BE%2058%25%20%E2%80%A2%20FE%2097%25-success)](https://github.com/SadmaFaahiim/Rentora/actions)
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

**Fraud Detection** — 6-detector engine (duplicate title, copied description, price anomaly vs market percentiles, missing images, unverified owner, rapid spam) with auto-scan + admin review queue

**Auth & Trust**

- Fresh **login/register redesign** (animated Dribbble-style auth page)
- Sign in with **username or email**; **duplicate-email registration now blocked** (serializer + DB unique constraint) with a readable error message
- Already-logged-in users are redirected from `/auth` to their dashboard

**Engineering**

- 170 automated tests (98 backend + 72 frontend) · coverage gates (BE ≥50%, FE ≥55%)
- Ruff + ESLint + Prettier with husky/lint-staged pre-commit hooks
- GitHub Actions CI (backend, frontend, lint, coverage-summary PR comment, coverage-history)
- Route-level code splitting (React.lazy) — smaller bundles

---

## 🗺️ Delivery Roadmap

> Tracked like a product backlog — every shipped phase is checked off.

| Phase     | Scope                                                                                             | Status                  |
| --------- | ------------------------------------------------------------------------------------------------- | ----------------------- |
| **1–2**   | React prototype with mock data                                                                    | ✅ Shipped              |
| **2.5**   | Frontend refactor — Vite, TS strict, Tailwind, Zustand, React Query, shadcn/ui                    | ✅ Shipped              |
| **3**     | Django backend — 10+ apps, JWT auth, full REST API, frontend integration                          | ✅ Shipped              |
| **4**     | Real-time chat (Django Channels, typing, read receipts, file upload) + real-time notifications    | ✅ Shipped              |
| **5**     | Payments — SSLCommerz + bKash, refunds, PDF receipts, invoices, security deposits, webhook audit  | ✅ Shipped              |
| **6**     | AI — recommendation engine (content/collaborative/hybrid) + price insight + fair-price prediction | ✅ Shipped              |
| **Bonus** | Roommate matching (profile + scoring + request flow)                                              | ✅ Shipped              |
| **Bonus** | Fraud engine (6 detectors, auto-scan, review queue)                                               | ✅ Shipped              |
| **Bonus** | Paid listing tiers (Free/Featured/Premium monetization)                                           | ✅ Shipped              |
| **Bonus** | Geo backend (bbox / radius / landmark queries)                                                    | ✅ Shipped              |
| **7**     | Map frontend (Leaflet, heatmap, university/metro proximity)                                       | ⏳ Next — geo API ready |
| **8**     | Docker Compose + production deployment + HTTPS                                                    | ⏳ Next — CI/CD done    |

---

## ✨ Features

**For Tenants**

- Browse and search verified room listings across Dhaka
- AI-powered room recommendations based on budget, area, and preferences
- Advanced filters (area, type, price range, amenities, gender preference)
- Geo search — filter by map viewport (`bbox`), radius around a point, or proximity to landmarks/metro stations
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

| Technology            | Purpose                       |
| --------------------- | ----------------------------- |
| React 18              | UI framework                  |
| TypeScript (strict)   | Type safety                   |
| Vite                  | Build tool                    |
| TailwindCSS v4        | Styling                       |
| shadcn/ui             | Component library             |
| React Router v6       | Client-side routing           |
| Zustand               | Client state management       |
| TanStack Query        | Server state + caching        |
| Axios                 | HTTP client with interceptors |
| React Hook Form + Zod | Form validation               |
| Motion                | Entrance/exit animation       |
| Sonner                | Toast notifications           |
| Vitest                | Unit tests + coverage         |

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

### Automated tests (170 total)

| Suite             | Count | Gate                                               |
| ----------------- | ----- | -------------------------------------------------- |
| Backend (Django)  | 98    | ✅ passing · coverage ≥ 50% lines                  |
| Frontend (Vitest) | 72    | ✅ passing · coverage ≥ 55% lines (currently ~97%) |

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
| `coverage-summary.yml` | Posts a coverage **PR comment** (badge + file-level detail) | PRs             |
| `coverage-history.yml` | Appends coverage history (protects against regression)      | pushes to main  |

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

| Method | Endpoint                      | Auth   | Description                                |
| ------ | ----------------------------- | ------ | ------------------------------------------ |
| POST   | `/api/v1/auth/register/`      | Public | Register (email must be unique)            |
| POST   | `/api/v1/auth/login/`         | Public | Login with email or username (returns JWT) |
| POST   | `/api/v1/auth/logout/`        | Auth   | Logout (blacklist token)                   |
| POST   | `/api/v1/auth/token/refresh/` | Public | Refresh access token                       |
| GET    | `/api/v1/auth/user/`          | Auth   | Get current user profile                   |
| PATCH  | `/api/v1/auth/user/`          | Auth   | Update profile                             |

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

> 💡 Screenshots can be regenerated with [`docs/tools/capture-screenshots.mjs`](docs/tools/capture-screenshots.mjs) — it drives headless Chrome, mints demo tokens via Django, and saves fresh PNGs into `docs/screenshots/`.

---

## 🖼️ Screenshots

**Roommate Matching** — find compatible flatmates by budget, area, lifestyle & gender preference:

<img width="1440" alt="Roommate Matching" src="docs/screenshots/roommates-matching.png" />

**Fraud Detection** — auto-scanned listings with risk scores & one-click re-scan from the landlord dashboard:

<img width="1440" alt="Fraud Detection Dashboard" src="docs/screenshots/fraud-detection.png" />

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
