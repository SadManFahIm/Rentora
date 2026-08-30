# Tier-2 Upgrades — Trust, Analytics & Infrastructure

A medium-sized upgrade batch on top of Phase 12, focused on making the
trust layer *learn*, the product *measurable*, the map *real*, and the
uploads *safer* — all self-hosted / free / open-source, with graceful
fallbacks everywhere so nothing existing breaks.

| Upgrade | Area | Status |
| --- | --- | --- |
| AI chat-safety classifier | Phase 12 — Chat Safety | ✅ Shipped |
| Self-hosted analytics + conversion funnel | Phase 10 — Growth | ✅ Shipped |
| Photo manipulation / watermark detection | Phase 12 — Photo Moderation | ✅ Shipped |
| OSRM road-network commute ETA | Phase 7 — Map | ✅ Shipped (opt-in) |
| ClamAV virus scan for chat uploads | Phase 4 — Chat | ✅ Shipped (opt-in) |
| KYC automated pre-screening | Phase 12 — Tenant KYC | ✅ Shipped |
| react-router v7 | Frontend | ✅ Shipped |

---

## 1. AI chat-safety classifier (`chat/classifier.py`)

A learned layer **on top of** the deterministic rules in `chat/safety.py`:

- Pure-stdlib **Naive Bayes** trained on a small hand-labelled corpus of
  real EN + BN rental conversations. Deterministic, trains in milliseconds
  at first use, no model files, no external service.
- **Unicode-aware tokenization** — the Bengali block (U+0980–U+09FF) is
  matched explicitly because Python's `\w` splits Bangla words at vowel
  signs.
- **Safety guarantees**: the model can only (a) raise a rule-clean message
  to *medium* (→ flag for human review) when its posterior ≥
  `CHAT_SAFETY_ML_FLAG_CONFIDENCE` (0.60), or (b) boost a rule-based
  medium to *high* at ≥ `CHAT_SAFETY_ML_BOOST_CONFIDENCE` (0.85). It can
  **never block** and never downgrades a rules verdict — a model mistake
  degrades to a queue item, never to a silently eaten message.
- The existing admin **chat-safety feed** (ChatSafetyEvent rows) is the
  human fallback queue; ML-only flags appear there with the
  `ml_classifier` detector key.
- Toggles: `CHAT_SAFETY_ML_ENABLED`, `CHAT_SAFETY_ML_FLAG_CONFIDENCE`,
  `CHAT_SAFETY_ML_BOOST_CONFIDENCE`.

## 2. Self-hosted analytics (`analytics/` app)

First-party product analytics — no vendor, no tracking pixel, data stays
on the server:

- `POST /api/v1/analytics/events/` — fire-and-forget capture
  (`event`, `category`, `path`, `session_id`, bounded `properties`).
  Auth optional (authenticated events are user-attributed), throttled
  (300/hour), payloads bounded server-side, **no PII** expected or stored.
- `GET /api/v1/analytics/summary/?days=` — admin dashboard snapshot:
  totals (events / sessions / active users), top events, top pages, daily
  volume, and the **conversion funnel** (`page_view → room_view →
  chat_started → booking_requested → booking_confirmed →
  payment_completed`, distinct authenticated users per step).
- Frontend: `track()` helper in `src/services/analytics.ts` (fire-and-forget
  via `fetch` + `keepalive`, silent on failure), `page_view` on every route
  change (Layout), `booking_requested` on Book Now (RoomModal).
- Admin UI: **Analytics** tab in the Trust & Safety Operations Center.
- Event data is append-only metadata; retention/aggregation jobs are future
  work (see Limitations).

## 3. Photo manipulation / watermark detection (`fraud/services/image_forensics.py`)

Pure-Pillow forensics on listing photos, wired into the fraud scan as the
new `manipulated_image` detector:

- **Block-level ELA consistency** — re-encodes at a known JPEG quality and
  compares 8×8 block error levels. A pasted region from another compression
  generation (the classic edit attack) spikes the max/min block ratio;
  honest full recompression (screenshots) stays uniform and is **not**
  flagged.
- **Watermark / caption band** — a bottom band far more uniform than the
  textured body suggests an overlay.
- **Editor EXIF** — `Software` naming heavy editors / AI tools (weak,
  non-blocking signal).
- **Tiny / low-quality** — files below 400px or ~25 KB are not real
  listing photos.
- Every finding is a *suspicion to review* with a 0–1 score; the detector
  reads at most 8 images, skips unreadable/missing files, and never fails
  a scan.

## 4. OSRM commute ETA (`rooms/osrm.py`)

Real road-network ETA for the map:

- `GET /api/v1/rooms/eta/?from_lat=&from_lng=&to_lat=&to_lng=&mode=car|cng|bus`
  — car → OSRM `driving` profile; CNG/bus are honestly-labelled congestion
  adjustments (×1.2 / ×1.35).
- **Cache-first** (15 min TTL) and **graceful fallback**: any failure
  (timeout, 5xx, disabled) returns `None` and `commute_eta` falls back to
  the existing straight-line/MRT heuristics — the map never breaks.
- **Opt-in** (`OSRM_ENABLED`): defaults off so existing behavior and tests
  are untouched; production points `OSRM_URL` at a self-hosted OSRM server
  (free, open-source; the public demo server works for dev).

## 5. ClamAV virus scan for chat uploads (`chat/antivirus.py`)

- Chat attachments keep their allow-list type + 10 MB size gates; when
  `CLAMAV_ENABLED=True` and a clamd daemon is reachable
  (`CLAMAV_HOST`/`CLAMAV_PORT`), uploaded bytes are scanned before anything
  is stored. A **positive detection rejects the file** (400).
- Any scanner failure degrades to **clean-by-default** — a message is never
  blocked because the scanner was unreachable.
- Tests mock the clamd socket seam; dev/CI need no daemon.

## 6. KYC automated pre-screening (`users/kyc_auto.py`)

Every tenant verification submission is scored automatically and the admin
queue shows an **approve/review recommendation + reasons**:

- Checks: document parses (image via Pillow or PDF magic bytes), **not
  reused across accounts** (pHash vs other users' recent docs — the classic
  same-scan-two-accounts tell), readable size (≥ 400px), profile
  completeness, and **attempt history from the append-only audit log**
  (rejections/needs-review, since `TenantVerification` is one-per-user).
- Scoring: 100 − penalties. Hard defects (unreadable / duplicate / tiny)
  **force** `recommend_review` regardless of score; everything else needs
  ≥ 70 to recommend approve.
- The **human decision remains the source of truth** — the screen only
  sorts the queue. Fields `auto_screen_score` / `auto_screen_result` /
  `auto_screen_detail` are exposed on the verification serializer and
  rendered as a chip in the admin KYC panel (hover for reasons).

## 7. react-router v7

`react-router` + `react-router-dom` upgraded 6.26 → **7.x** (both packages
now, `react-router-dom` re-exports from `react-router`). Plain
`BrowserRouter`/`Routes`/`Route` usage is fully compatible; `tsc`, all 312
frontend tests and the production build pass unchanged, and **npm audit is
now clean (0 vulnerabilities)** — the last 2 moderates (v6) are gone.

---

## Config surface

| Setting | Default | Purpose |
| --- | --- | --- |
| `CHAT_SAFETY_ML_ENABLED` | `True` | learned chat-safety layer on/off |
| `CHAT_SAFETY_ML_FLAG_CONFIDENCE` | `0.60` | ML-only flag threshold |
| `CHAT_SAFETY_ML_BOOST_CONFIDENCE` | `0.85` | ML medium→high boost threshold |
| `OSRM_ENABLED` | `False` | road-network ETA on/off (safe rollout) |
| `OSRM_URL` | public demo | self-host OSRM in production |
| `OSRM_TIMEOUT_SECONDS` / `OSRM_CACHE_TTL` | `3` / `900` | latency + cache bounds |
| `CLAMAV_ENABLED` | `False` | virus scanning on chat uploads |
| `CLAMAV_HOST` / `CLAMAV_PORT` | `127.0.0.1` / `3310` | clamd socket |

## Tests

57 new backend tests (569 total backend, 312 frontend):
`chat/test_classifier.py` (11) · `analytics/tests.py` (6) ·
`fraud/test_image_forensics.py` (10) · `rooms/test_osrm.py` (12) ·
`chat/test_antivirus.py` (8) · `users/test_kyc_auto.py` (10). All network
calls are mocked (OSRM `_http_get`, ClamAV `_clamd_client`); no suite needs
a live routing server, a virus daemon, or network access.

## Known limitations

- The ML classifier is a deliberately **weak** second opinion trained on a
  small corpus — treat its flags as queue-sorting, not proof. Retraining /
  a richer corpus / a real model file is future work.
- Funnel numbers count distinct *authenticated* users; anonymous traffic
  under-reports until more events are wired (room_view, chat_started,
  booking_confirmed, payment_completed are defined but not yet emitted by
  every surface).
- OSRM CNG/bus ETAs are congestion-adjusted driving times, not native
  profiles — honest labels are included in the payload.
- ClamAV requires a clamd daemon (free/OSS) — opt-in, disabled by default.
- ELA/watermark heuristics are heuristics: threshold tuning against real
  listing photo distributions is recommended before production reliance.
- No analytics retention/aggregation job yet — `Event` rows are append-only.

## Future work

- RAG-powered Copilot (grounded listing Q&A), full EN/BN i18n.
- Self-hosted OSRM provisioning in the Phase 8 Docker compose.
- Analytics retention/rollup + more funnel events.
- Model retraining pipeline + A/B toggle for the ML classifier.
