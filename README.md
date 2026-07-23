# 🏠 Rentora — AI-Powered Room Rental Platform

> Bangladesh's smartest room rental platform. Find verified, affordable rooms with AI-powered recommendations, real-time chat, and secure payments.

[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6?logo=typescript)](https://typescriptlang.org)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ Features

**For Tenants**
- Browse and search verified room listings across Dhaka
- AI-powered room recommendations based on budget, area, and preferences
- Advanced filters (area, type, price range, amenities, gender preference)
- Wishlist rooms for later
- Book rooms with one click
- Real-time chat with landlords (WebSocket)
- Dashboard with booking stats and notifications

**For Landlords**
- Create and manage room listings with multiple images
- Receive booking requests with approve/reject workflow
- Get notified on new bookings and reviews
- Dashboard with revenue stats, ratings, and listing analytics

**Platform Features**
- JWT authentication (register/login/refresh/logout)
- Real-time notifications (booking updates, new reviews)
- Review system with verified stay badges
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
│   │   ├── pages/             # Route pages (Home, Rooms, Map, Chat, Dashboard, Auth)
│   │   ├── services/          # API service layer (auth, rooms, bookings, wishlist, etc.)
│   │   ├── hooks/             # TanStack Query hooks (useRooms, useAuth, useBookings)
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
│   ├── rooms/                 # Room listings + images + CRUD
│   ├── bookings/              # Bookings + Reviews + signals
│   ├── wishlist/              # Wishlist toggle
│   ├── notifications/         # Auto-notifications + API
│   ├── dashboard/             # Aggregated stats endpoint
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
| GET | `/api/v1/rooms/` | Public | List rooms (filter/search/sort) |
| GET | `/api/v1/rooms/:id/` | Public | Room detail |
| POST | `/api/v1/rooms/` | Auth | Create listing |
| PUT/PATCH | `/api/v1/rooms/:id/` | Owner | Update listing |
| DELETE | `/api/v1/rooms/:id/` | Owner | Delete listing |

**Filters:** `?area=Dhanmondi&room_type=studio&price__gte=5000&price__lte=15000&is_available=true&search=cozy&ordering=-price`

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

---

## 🗺️ Roadmap

- [x] **Phase 1-2:** Frontend prototype (React, mock data)
- [x] **Phase 2.5:** Frontend refactor (Vite, TypeScript, Tailwind, Zustand, React Query)
- [x] **Phase 3:** Django backend (6 apps, JWT auth, full REST API, frontend integration)
- [ ] **Phase 4:** Real-time chat (Django Channels, WebSocket) — *in progress*
- [ ] **Phase 5:** Payment integration (SSLCommerz + bKash)
- [ ] **Phase 6:** AI features (recommendation engine, fraud detection, price prediction)
- [ ] **Phase 7:** Map integration (Leaflet.js, heatmap, university/metro proximity)
- [ ] **Phase 8:** Docker + CI/CD + deployment

---

## 📸 Screenshots
<img width="1920" height="2178" alt="RentRoom_BD" src="https://github.com/user-attachments/assets/8e7cd2b5-174e-4855-a8d6-beea394a12cc" /> 
<img width="1920" height="1433" alt="RentRoom_BD__1_" src="https://github.com/user-attachments/assets/e03dcd15-632b-4e2d-8659-de4bc2946f43" />
<img width="1920" height="927" alt="RentRoom_BD__3_" src="https://github.com/user-attachments/assets/6dc84e24-8d02-4cf5-a6a6-3ff926b21371" />
<img width="1920" height="927" alt="RentRoom_BD__2_" src="https://github.com/user-attachments/assets/6b958b77-127f-4424-8b62-76b6f6a09520" />



---

## 👨‍💻 Developer

**Sadman Chowdhury Fahim**
- GitHub: [@SadManFahIm](https://github.com/SadManFahIm)

---

## 📄 License

This project is licensed under the MIT License.
