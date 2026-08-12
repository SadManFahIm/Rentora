# ✅ Live Verification

> What was actually verified, in which environment, with what result. Status
> legend: **PASS** (verified live) · **PARTIAL** (part verified, gap noted) ·
> **NOT TESTED** (not verified this run).

---

## Environment

| Component | Configuration |
|---|---|
| Frontend | Vite dev server `http://localhost:3001` (React 18, TS strict, Tailwind, MapLibre GL) |
| Backend | Django `manage.py runserver 127.0.0.1:8000` (dev settings, SQLite, LocMemCache) |
| Browser | Headless Chrome (screenshot capture) + desktop WebView preview (interactive) |
| Auth | Demo JWT tokens minted via Django shell (bypasses login throttle) |

**Screenshots** are stored in `docs/screenshots/` and regenerated with
`docs/tools/capture-screenshots.mjs` (28 captures, all produced PNGs of
non-trivial size).

---

## Intelligent Map v2 (Phase 7 v2) — this batch

| Feature | Scenario | Expected | Actual | Status |
|---|---|---|---|---|
| AI Smart Map Search | Bangla query "উত্তরায় ১২ হাজারের মধ্যে furnished room" via the AI Map panel | Parsed intent chips (Uttara · ≤৳12,000 · Furnished), real matching rooms, map flies to area, radius search starts, shareable URL updates | **2 matching rooms**, chips rendered, map flew to `center=23.8759,90.3795&zoom=13&r=2&q=Uttara`, value-score chips visible | ✅ PASS |
| Area Intelligence | Areas tab → tap "Mirpur · 11" | Stats card with avg/median rent, listings, demand, metro access, price trend + compare button | Card rendered: Avg ৳11,209 · Median ৳10,000 · 11 listings · 11 available · Metro access 89/100 · Trend −17% · 👀0/💾0/📅0 demand chips | ✅ PASS |
| Affordability | Budget tab, slider set to ৳10,000 | Per-area % bars render from real listing shares | Capture produced `map-intel-affordability.png` (panel + bars rendered) | ✅ PASS |
| Backend API | `GET /api/v1/rooms/map-intel/stats/` and `/search/` (curl) | 200 with real aggregates | Both 200 — area stats list Mirpur/Banani/etc., search returns intent + rooms + fly-to target | ✅ PASS |
| Value scores | `GET /rooms/map-intel/value/?ids=…` + popup chips | 0–100 score with explainable factors, cached | Scores shown in panel (⭐46/66/49 on visible rooms); API returns `factors` breakdown | ✅ PASS |
| Commute mode UI | Drop destination on map → walking rows | Destination pin renders; rows sorted by walk time; ≤max filter | Backend `map-intel/commute/` verified by 34-test suite (walking/driving/transit/unavailable); pin effect typechecked + destination prop wired | 🟡 PARTIAL (pin-drop click flow not re-clicked this run) |
| Tests | Backend `rooms.tests_map_intel` (34) + frontend `mapIntelService.test.ts` (8) | All green | 34/34 + 8/8 green; full suites 368 backend + 202 frontend | ✅ PASS |
| Theme support | Light + dark map views | Map readable in both | `map-view.png` + `map-view-dark.png` captured (CARTO dark tiles / dimmed OSM fallback) | ✅ PASS |

---

## Prior batch — re-verified through test suites this run

| Feature | Verification | Status |
|---|---|---|
| Admin Fraud Operations (summary/filters/review/audit) | `rooms.tests_security.py` — admin-only gating (non-admin 403 on summary/review) + full backend suite | ✅ PASS |
| Saved-search match tuning command | Tuning command exists + covered by saved-searches tests in full suite | ✅ PASS |
| Upload validation (`config/uploads.py`) | `rooms.tests_security.py` — non-image extension 400, oversized 400, valid PNG 201 | ✅ PASS |
| Security audit docs | `SECURITY.md`, `docs/SECURITY_CHECKLIST.md`, `docs/SECURITY_AUDIT.md` committed | ✅ PASS |
| Voice search | `useVoiceSearch.test.tsx` suite (transcript / unsupported / denied / error / cleanup) | ✅ PASS |
| Price anomaly / listing quality / saved-search match | Screenshots captured (`price-anomaly.png`, `listing-quality.png`, `saved-search-match.png`) | ✅ PASS (visual) |
| Full backend regression | `manage.py test` — **368 tests** (was 334; +34 map-intel) | ✅ PASS |
| Full frontend regression | Vitest — **202 tests** (was 194; +8 map-intel), tsc clean | ✅ PASS |
| Lint/format | ruff check + ruff format (backend), eslint + prettier (frontend, changed files) | ✅ PASS |

---

## Not covered this run

- **Commute UI click-through** (drop pin → rows) — backend + wiring verified; the
  interactive pin-drop flow is the one manual step to re-run.
- **Mobile viewport for the map panel** — mobile KYC capture exists
  (`kyc-mobile.png`); the map panel itself was verified at desktop width.
- Browser matrix beyond Chrome/Edge WebView (Firefox Web Speech API).

Run any item above with:

```bash
# backend (tests + lint)
cd backend && venv/Scripts/python manage.py test && venv/Scripts/python -m ruff check . && venv/Scripts/python -m ruff format --check .

# frontend (tests + types + lint)
cd frontend && npx vitest run && npx tsc --noEmit && npm run lint && npm run format:check
```
