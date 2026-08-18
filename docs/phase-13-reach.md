# Phase 13 — Reach (SMS OTP, WhatsApp sharing, area landing pages)

Phase 13 widens **how Rentora reaches users** — phone-based sign-in for the
Bangladeshi market, one-tap WhatsApp sharing of listings, SEO landing pages
per Dhaka area, and a Lighthouse performance gate in CI.

Scope notes up front (honest):

- **This phase is web-only.** A native React Native app is still a separate,
  unfunded track. What ships here are the web-feasible reach features plus a
  mobile-product plan in [docs/MOBILE_APP_PLAN.md](docs/MOBILE_APP_PLAN.md).
- **SMS sending is gated off by default.** No gateway credentials ship with
  the repo. The provider contract is real and tested, but until you plug in a
  gateway (`SMS_OTP_ENABLED=True`) the SMS endpoints answer `503`.
- **Area pages are an SEO story with SPA limits.** These are indexable
  HTML-rendered routes (per-area titles/meta + a static `sitemap.xml` +
  `robots.txt`), not full server-side rendering. The site is still a React
  SPA, so heavy JS-rendered content (the room list itself) relies on Google
  rendering the SPA; the per-area `<title>`/description and the sitemap are
  what make each URL crawlable. Full SSR/hydration remains a documented
  future improvement.

## What ships

### 1. SMS OTP sign-in (`users` app)

- `POST /api/v1/auth/sms/request/` — `{phone}` → issues a one-time code and
  returns the **masked** number (`+8801••••78`) + a resend cooldown.
- `POST /api/v1/auth/sms/verify/` — `{phone, code}` → exchanges the code for
  JWTs. A phone with no account is **auto-registered** (username
  `bd<last-10-digits>`, unverified password — the user sets one later).
- Codes are hashed with **SHA-256** in the DB (`SmsOtpChallenge`), TTL 600s,
  max 5 attempts, resend cooldown 30s, single active challenge per phone.
- Phone normalization: any `01XXXXXXXXX` / `+8801XXXXXXXXX` / `8801...` input
  becomes `+8801XXXXXXXXX`.
- **Providers** (the `users.sms` contract — one function, `send_sms`):
  - `console` — logs the code to the server log (zero-config local dev/CI).
  - `http` — POSTs to `SMS_GATEWAY_URL` with `SMS_GATEWAY_API_KEY` +
    `SMS_SENDER_ID`. Plug in Twilio / GreenWeb / any gateway behind it.
- **Master switch** `SMS_OTP_ENABLED` (default `False`). When off, both
  endpoints return `503` so no traffic is silently dropped and no fake codes
  are "sent". When on, the frontend shows the phone-sign-in box.
- 19 new tests (`users/test_sms_otp.py`), including the disabled→503 path,
  masked-phone formatting, cooldown/attempt enforcement and auto-registration.

### 2. WhatsApp listing share (AI share summary)

- **`GET /api/v1/copilot/share-summary/<id>/`** (public) — a compact,
  deterministic summary built **only from the listing's public fields**
  (title · area · price · room type · size · top amenities · verified badge ·
  availability). `{id, title, price, area, area_display, summary}`. No owner
  contact details ever leak; 404 for missing/unavailable rooms.
- **Frontend** — a **Share on WhatsApp** button on every room card and in the
  room modal. It calls the AI summary endpoint, falls back to a
  deterministic client-side summary when the AI call fails (or the backend is
  down), and opens `https://wa.me/?text=…` pre-filled with the summary + the
  room's deep link. `src/lib/share.ts` (unit-tested) builds the wa.me URL
  safely (pre-encoded, length-capped).
- 8 new tests in `copilot/test_listing_qa.py` (deterministic content,
  no-forbidden-fields, endpoint public / 404 paths).

### 3. Area landing pages + SEO

- **`/rooms/:areaSlug`** — a crawlable per-area page (Dhanmondi, Mirpur,
  Gulshan, Banani, Mohammadpur, Uttara, Bashundhara, Tejgaon, Badda, Old
  Dhaka) with its own `<title>` ("Rooms for rent in Dhanmondi, Dhaka"),
  meta description, area heading, description text, and the live room grid.
  `?room=<id>` deep-links straight into the room modal for shared links.
- **Navbar “Areas” dropdown** — quick navigation to every area page.
- **`npm run generate:sitemap`** (`scripts/generate-sitemap.mjs`) — writes
  `public/sitemap.xml` (5 core routes + 10 area routes). Base URL defaults to
  `https://rentora.example.com` — override with `SITEMAP_BASE_URL` at deploy.
- **`public/robots.txt`** — allows the crawlable routes, disallows
  `/auth` and `/dashboard`, points crawlers at the sitemap.
- `useSeo()` hook centralizes title/meta updates (also used by the area page).

### 4. Lighthouse gate (CI)

- **`scripts/lighthouse-gate.mjs`** runs Lighthouse (via `chrome-launcher`)
  against the **built** app and fails the job below the threshold
  (`--min-score`, default 70). Local run: **Performance 70 / threshold 70
  PASS**.
- **CI job `lighthouse`** — after the frontend job: `vite build` →
  `vite preview` on :4173 → poll until ready → run the gate → upload the
  Lighthouse JSON report as an artifact.

## Configuration

| Setting (base.py, `os.getenv`)            | Default | Purpose                                  |
| ----------------------------------------- | ------- | ---------------------------------------- |
| `SMS_OTP_ENABLED`                          | `False` | Master switch; off → SMS endpoints 503   |
| `SMS_PROVIDER`                             | `console` | `console` (log) or `http` (gateway POST) |
| `SMS_GATEWAY_URL` / `SMS_GATEWAY_API_KEY` / `SMS_SENDER_ID` | `""` | HTTP provider connection                  |
| `SMS_OTP_TTL_SECONDS`                      | `600`   | Challenge lifetime                       |
| `SMS_OTP_MAX_ATTEMPTS`                     | `5`     | Max verify attempts per challenge        |
| `SMS_OTP_RESEND_COOLDOWN_SECONDS`          | `30`    | Min seconds between requests             |

Backend env vars are documented in `backend/.env.example`.

## API

| Method | Endpoint                            | Auth   | Description                                |
| ------ | ----------------------------------- | ------ | ------------------------------------------ |
| POST   | `/api/v1/auth/sms/request/`         | Public | Request an SMS OTP (503 when disabled)     |
| POST   | `/api/v1/auth/sms/verify/`          | Public | Verify code → JWTs (auto-registers phone)  |
| GET    | `/api/v1/copilot/share-summary/<id>/` | Public | Deterministic share-ready listing summary |

## Tests

- Backend: **689 tests pass** (was 667; +22 new — 19 SMS + 3 share-summary
  API). `users.test_sms_otp` + `copilot.test_listing_qa` covered directly.
- Frontend: **322 existing + 11 new** (`lib/share.test.ts` 5, `data/areas`
  5, `copilotService` 1) all pass; `tsc --noEmit`, ESLint (0 errors) and
  `vite build` clean.
- Migration: `users/0010_smsotpchallenge.py` (created + applied to the dev DB).

## Screenshots

- `docs/screenshots/phase13-area-page.png` — `/rooms/dhanmondi` area page
  (SEO title verified).
- `docs/screenshots/phase13-whatsapp-share.png` — room modal **Share on
  WhatsApp** button.
- `docs/screenshots/phase13-sms-login.png` — the phone sign-in box in the
  auth dialog.

Captured by `frontend/scripts/capture_phase13_shots.mjs` (Playwright, real
stack). All three are public pages, so the script does **not** log in.

## What this phase does NOT do (deferred)

- **React Native app** — see [docs/MOBILE_APP_PLAN.md](docs/MOBILE_APP_PLAN.md).
- **Real SMS gateway credentials** — wire up `SMS_PROVIDER=http` + a gateway
  in production settings, then flip `SMS_OTP_ENABLED=True`.
- **Server-side rendering** — the SPA still renders client-side; area pages
  are crawlable metadata + sitemap, not SSR.
- **SMS verification of existing account phone changes** / phone-verified
  badges — future phases.