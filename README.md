# 🏠 Rentora — AI-Powered Room Rental Platform

> Bangladesh's smartest room rental platform. Find verified, affordable rooms with AI-powered recommendations, real-time chat, secure payments, roommate matching, and fraud detection.

[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6?logo=typescript)](https://typescriptlang.org)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![DRF](https://img.shields.io/badge/DRF-3.15-a30000?logo=django)](https://www.django-rest-framework.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

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
- Dashboard with revenue stats, ratings, listing analytics, and fraud risk cards with one-click re-scan

**Platform Features**
- JWT authentication (register/login/refresh/logout)
- Real-time notifications (booking updates, reviews, roommate requests, fraud flags)
- Review system with verified stay badges
- **6-detector fraud engine** — duplicate titles, copied descriptions, suspicious pricing (vs. market percentiles), missing images, unverified owners, rapid listing spam
- Responsive design (mobile, tablet, desktop)
- Dark mode support
- API documentation (Swagger UI + ReDoc)
- Input sanitization and rate limiting

---

## 🏗️ Tech Stack

### Frontend
| Technology | Purpose |
|---|---|
| React 18 | UI framework |
| TypeScript (strict) | Type safety |
| Vite | Build tool |
| TailwindCSS v4 | Styling |
| shadcn/ui | Component library |
| React Router v6 | Client-side routing |
| Zustand | Client state management |
| TanStack Query | Server state + caching |
| Axios | HTTP client with interceptors |
| React Hook Form + Zod | Form validation |
| Sonner | Toast notifications |

### Backend
| Technology | Purpose |
|---|---|
| Django 5.2 | Web framework |
| Django REST Framework | REST API |
| Django Channels | WebSocket support |
| Daphne | ASGI server |
| SimpleJWT | JWT authentication |
| dj-rest-auth + django-allauth | Auth endpoints |
| django-filter | API filtering |
| drf-spectacular | OpenAPI docs |
| bleach | Input sanitization |
| difflib | Similarity detection (fraud engine) |
| PostgreSQL 16 | Production database |
| SQLite | Development database |
| Redis | Channel layer + caching |

---

## 📁 Project Structure

```
Rentora/
├── frontend/                  # React SPA
│   ├── src/
│   │   ├── components/        # UI components (Navbar, RoomCard, ChatWindow, etc.)
│   │   │   └── ui/            # shadcn/ui primitives
│   │   ├── pages/             # Route pages (Home, Rooms, Map, Chat, Dashboard, Roommates, Auth)
│   │   ├── services/          # API service layer (auth, rooms, bookings, roommates, fraud, etc.)
│   │   ├── hooks/             # TanStack Query hooks (useRooms, useAuth, useRoommates, useFraud)
│   │   ├── stores/            # Zustand stores (ui, wishlist, notifications)
│   │   ├── context/           # React context (AppContext for auth)
│   │   ├── types/             # TypeScript type definitions
│   │   ├── config/            # Environment config
│   │   ├── data/              # Mock data (chat placeholder, filter constants)
│   │   └── styles/            # TailwindCSS config + global styles
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── backend/                   # Django REST API
│   ├── config/                # Project config (settings, urls, asgi, middleware)
│   │   └── settings/          # Split settings (base, dev, prod)
│   ├── users/                 # Custom User model + auth
│   ├── rooms/                 # Room listings + images + geo queries (bbox/radius/landmarks)
│   ├── bookings/              # Bookings + Reviews + signals
│   ├── wishlist/              # Wishlist toggle
│   ├── notifications/         # Auto-notifications + API
│   ├── dashboard/             # Aggregated stats endpoint
│   ├── chat/                  # Real-time chat (Channels, WebSocket, presence)
│   ├── payments/              # SSLCommerz + bKash, refunds, invoices, receipts
│   ├── recommendations/       # Content-based + collaborative + hybrid engine
│   ├── pricing/               # Market stats + price insight + fair-price prediction
│   ├── roommates/             # Roommate profiles + weighted matching algorithm
│   ├── fraud/                 # 6-detector fraud engine + auto-scan + review queue
│   ├── manage.py
│   └── requirements.txt
│
└── docs/                      # Documentation
```

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

# Seed sample data (8 rooms with images)
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
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register/` | Public | Register new user |
| POST | `/api/v1/auth/login/` | Public | Login (returns JWT) |
| POST | `/api/v1/auth/logout/` | Auth | Logout (blacklist token) |
| POST | `/api/v1/auth/token/refresh/` | Public | Refresh access token |
| GET | `/api/v1/auth/user/` | Auth | Get current user profile |
| PATCH | `/api/v1/auth/user/` | Auth | Update profile |

### Rooms
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/rooms/` | Public | List rooms (filter/search/sort/geo) |
| GET | `/api/v1/rooms/:id/` | Public | Room detail |
| POST | `/api/v1/rooms/` | Auth | Create listing |
| PUT/PATCH | `/api/v1/rooms/:id/` | Owner | Update listing |
| DELETE | `/api/v1/rooms/:id/` | Owner | Delete listing |
| GET | `/api/v1/rooms/landmarks/` | Public | List landmarks (for `near_landmark`) |

**Text filters:** `?area=Dhanmondi&room_type=studio&price__gte=5000&price__lte=15000&is_available=true&search=cozy&ordering=-price`

**Geo filters:**
- `bbox=min_lng,min_lat,max_lng,max_lat` — map viewport (leaflet `getBounds()`)
- `near_lat=23.75&near_lng=90.39&radius_km=2` — radius around a point (nearest-first)
- `near_landmark=mirpur-10-metro&radius_km=3` — radius around a named landmark/metro station

### Bookings
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/bookings/` | Auth | My bookings (tenant + landlord) |
| POST | `/api/v1/bookings/` | Auth | Create booking request |
| PATCH | `/api/v1/bookings/:id/` | Auth | Update status (role-gated) |

### Reviews
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/reviews/?room=:id` | Public | Reviews for a room |
| POST | `/api/v1/reviews/` | Auth | Create review (requires approved booking) |

### Wishlist
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/wishlist/` | Auth | My wishlisted rooms |
| POST | `/api/v1/wishlist/toggle/` | Auth | Toggle wishlist (add/remove) |

### Notifications
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/notifications/` | Auth | My notifications |
| PATCH | `/api/v1/notifications/:id/` | Auth | Mark as read |
| POST | `/api/v1/notifications/mark-all-read/` | Auth | Mark all read |
| GET | `/api/v1/notifications/unread-count/` | Auth | Unread count |

### Dashboard
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/dashboard/stats/` | Auth | User stats (tenant + landlord) |

### Chat
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET/POST | `/api/v1/chat/rooms/` | Auth | List / create chat rooms |
| GET | `/api/v1/chat/rooms/:id/messages/` | Auth | Messages in a room |
| POST | `/api/v1/chat/rooms/:id/messages/` | Auth | Send a message |
| GET | `/api/v1/chat/online-status/` | Auth | Online status of users |
| POST | `/api/v1/chat/upload/` | Auth | Upload a chat attachment |
| WS | `/ws/chat/:room_id/` | Auth | Real-time chat socket (typing, read receipts) |

### Payments
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/payments/initiate/` | Auth | Initiate a payment (SSLCommerz) |
| POST | `/api/v1/payments/bkash/initiate/` | Auth | Initiate a bKash payment |
| POST | `/api/v1/payments/bkash/callback/` | Public | bKash gateway callback |
| POST | `/api/v1/payments/sslcommerz/success\|fail\|cancel/` | Public | SSLCommerz callbacks |
| GET | `/api/v1/payments/` | Auth | My payment history |
| GET | `/api/v1/payments/:id/` | Auth | Payment detail / receipt |
| POST | `/api/v1/payments/:id/refund/` | Auth | Request a refund |
| GET | `/api/v1/payments/summary/` | Auth | Payment summary |

### Recommendations
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/recommendations/?limit=N` | Auth | Hybrid room recommendations |

### Pricing (AI)
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/pricing/predict/` | Auth | Predict fair price for a new listing |
| GET | `/api/v1/pricing/insight/:room_id/` | Public | Price insight vs market for a room |
| GET | `/api/v1/pricing/market-stats/?area=X&room_type=Y` | Public | Raw market stats |

### Roommates
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET/PUT | `/api/v1/roommates/profile/` | Auth | Get / upsert my roommate profile |
| GET | `/api/v1/roommates/matches/` | Auth | Best-first scored match suggestions |
| GET/POST | `/api/v1/roommates/requests/` | Auth | My requests (incoming + outgoing) / send one |
| POST | `/api/v1/roommates/requests/:id/action/` | Receiver | Approve or reject a request |

### Fraud Detection
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/fraud/rooms/:room_id/status/` | Public | Public badge data (drives "under review" badge) |
| GET | `/api/v1/fraud/reports/` | Auth | Reports (owner: own rooms; admin: all) — filter by `status`/`severity` |
| POST | `/api/v1/fraud/rooms/:room_id/scan/` | Owner/Admin | Re-run the detector on a room |
| POST | `/api/v1/fraud/reports/:report_id/review/` | Admin | Mark reviewed / dismissed |

### Documentation
| Endpoint | Description |
|---|---|
| `/api/v1/docs/` | Swagger UI |
| `/api/v1/redoc/` | ReDoc |
| `/api/v1/schema/` | OpenAPI schema (YAML) |

---

## 🔐 Security

- JWT authentication with access/refresh token rotation
- Rate limiting (auth: 10/hr per IP, anon: 100/hr, user: 1000/hr)
- Input sanitization via bleach on all user-generated text
- CORS configured (dev: all origins, prod: pinned domains)
- Custom error handler with consistent JSON envelope
- Production security headers (HSTS, XSS filter, content-type nosniff)
- **Fraud engine** auto-scans every new listing (duplicate title, copied description, price anomalies vs. market percentiles, missing images, unverified owner, rapid listing) — flagged listings go into an admin review queue

---

## 🗺️ Roadmap

- [x] **Phase 1-2:** Frontend prototype (React, mock data)
- [x] **Phase 2.5:** Frontend refactor (Vite, TypeScript, Tailwind, Zustand, React Query)
- [x] **Phase 3:** Django backend (10 apps, JWT auth, full REST API, frontend integration)
- [x] **Phase 4:** Real-time chat (Django Channels, WebSocket — typing indicators, online status, read receipts, file upload, search) + real-time notifications
- [x] **Phase 5:** Payment integration (SSLCommerz + bKash, refunds, PDF receipts, invoices, security deposits, payment schedules, webhook security + audit log, full frontend integration)
- [x] **Phase 6:** AI features (recommendation engine — content-based + collaborative + hybrid; price insight + fair-price prediction; **fraud detection** — 6-detector engine with auto-scan + review queue)
- [ ] **Phase 7:** Map frontend (Leaflet.js, heatmap, university/metro proximity) — *geo backend done: bbox/radius/landmark queries ready*
- [x] **Roommate Matching:** profile + weighted scoring (budget/area/room-type/gender/lifestyle) + request/approve flow
- [ ] **Phase 8:** Docker + CI/CD + deployment

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

## 🧑‍💻 Demo Users

> Seed the database first (see [Getting Started](#-getting-started)), then sign in with any of these accounts:

| Role | Username | Password | What to explore |
|---|---|---|---|
| 🏠 Landlord | `rahim.hossain` | `demo12345` | Roommate matches (Sabbir 87%, Nadia 76%), room listing |
| 🏠 Landlord | `nadia.islam` | `demo12345` | Shared Premium Gulshan listing |
| 🏠 Landlord | `sabbir.rahman` | `demo12345` | Student Room Azimpur listing |
| 🏠 Landlord | `farhana.akter` | `demo12345` | Modern Studio Mirpur listing |
| 🏠 Landlord | `tanvir.islam` | `demo12345` | Fraud dashboard (Executive Single Banani + re-scan) |

**Tips**
- `rahim.hossain` has a roommate profile — log in and open **Roommates** to see live match scores.
- `tanvir.islam` has listings — open **Dashboard → Fraud** to see the risk cards and try **Re-scan**.
- All accounts use the shared demo password `demo12345`.

---

## 👨‍💻 Developer

**Sadman Chowdhury Fahim**
- GitHub: [@SadManFahIm](https://github.com/SadManFahIm)

---

## 📄 License

This project is licensed under the MIT License.
