# 📱 Progressive Web App (Phase 12)

Rentora is installable as a native-feeling app on desktop (Chrome/Edge) and
mobile (Android Chrome/Edge, iOS Safari) — without a separate mobile codebase.

- **P0 (shipped):** manifest → icons → install UX → standalone → deep links →
  security → performance.
- **P1 (shipped):** offline search over cached PUBLIC listings, offline action
  replay (background sync), periodic public-cache refresh, splash screens,
  dark maskable icon, iOS install hint, Lighthouse audit.

---

## Architecture

```
Browser install flow:
  manifest.webmanifest (name/icons/display/start_url/shortcuts)
        └─ index.html <link rel="manifest"> + apple-mobile-web-app-* meta
        └─ beforeinstallprompt ─► usePwaInstall ─► "Install app" CTA (native prompt)
        └─ (display-mode: standalone) ─► installed state ─► CTA disappears

Service worker (sw.js) — two responsibilities, one file:
  ├─ Web Push  (unchanged): push → notification → click → navigate
  └─ Static cache (new): versioned "rentora-static-v1"
        ├─ precache: /, manifest, favicon, icon-192, icon-512
        ├─ static assets (js/css/png/svg/ico/webp/woff2/json): cache-first
        ├─ navigations: network-first → cached app shell (offline)
        └─ NEVER: /api/* — auth, private, admin, fraud & payment data
```

---

## Files

| File | Purpose |
|---|---|
| `frontend/public/manifest.webmanifest` | Web app manifest (see below) |
| `frontend/public/icons/` | 192/512 standard, 512 maskable, 180 apple-touch, 32/48/96/144 favicons |
| `frontend/public/favicon.svg` | SVG favicon (also used as the push-notification icon) |
| `frontend/public/robots.txt` | SEO — allow-all crawl policy + sitemap placeholder |
| `frontend/index.html` | Manifest link, theme-color, apple-mobile-web-app-* meta, viewport-fit |
| `frontend/public/sw.js` | Push + conservative static caching, versioned, self-cleaning |
| `frontend/src/lib/pwa.ts` | Pure policy helpers (dismiss cooldowns, standalone, manifest validation) |
| `frontend/src/hooks/usePwaInstall.ts` | `beforeinstallprompt` lifecycle + native prompt |
| `frontend/src/hooks/usePwaUpdate.ts` | "New version available" Refresh/Later detection |
| `frontend/src/hooks/useOnline.ts` | Offline state |
| `frontend/src/lib/offlineDb.ts` | IndexedDB offline cache (PUBLIC data only) + offline action queue + offline filter |
| `frontend/src/lib/backgroundSync.ts` | Offline action replay (wishlist / saved-search) |
| `frontend/src/lib/periodicSync.ts` | Periodic Background Sync registration (Chromium/installed only) |
| `frontend/src/hooks/useBackgroundSync.ts` | Sync listeners (SW message, online, visibility) + periodic refresh |
| `frontend/src/hooks/useOfflineCacheStatus.ts` | "Showing cached rooms" status for the Rooms page pill |
| `frontend/src/components/BangladeshFlag/` | Inline SVG flag (renders everywhere, unlike the emoji) |
| `frontend/src/components/PwaInstallPrompt/` | Subtle "Install app" CTA (navbar) |
| `frontend/src/components/PwaBanners/` | Offline + new-version banners |
| `scripts/generate_pwa_icons.py` | Reproducible icon generation (Pillow) |
| `scripts/validate-pwa.mjs` | CI validation of the *built* manifest/icons/sw |

---

## Manifest

`frontend/public/manifest.webmanifest`:

| Field | Value |
|---|---|
| `name` / `short_name` | Rentora — Smart Rental Platform / Rentora |
| `start_url` / `scope` | `/` / `/` |
| `display` | `standalone` |
| `orientation` | `portrait-primary` |
| `theme_color` | `#ea580c` (design-token brand, Tailwind orange-600) |
| `background_color` | `#ffffff` |
| `icons` | 192 any · 512 any · 512 maskable |
| `shortcuts` | Search Rooms `/rooms` · Explore Map `/map` · Post Listing `/dashboard?tab=listings` |

`start_url`/`scope` are root-relative so they survive subpath deployment, and
all icon paths are root-absolute (`/icons/...`), matching how the app is built.

### Icons

Generated from the brand (orange gradient rounded square + white house) with
`scripts/generate_pwa_icons.py`:

- **standard** 192/512: rounded-square app icon
- **maskable** 512: full-bleed square, house inside the 80 % safe zone
- **apple-touch** 180 + **favicons** 32/48/96/144

Regenerate after a brand change: `python scripts/generate_pwa_icons.py`.

---

## Installation experience

- The browser's `beforeinstallprompt` is captured and **prevented by default** —
  Rentora never fires a surprise install popup.
- A subtle **"Install app"** button appears in the navbar (desktop) only when:
  1. the browser offers an install prompt,
  2. the app is not already installed (`appinstalled` / `display-mode: standalone`),
  3. the user hasn't dismissed it in the last 7 days.
- Clicking it shows the browser's **native** install prompt (never a fake UI).
- After install, the CTA disappears for good; after a dismissal it cools off
  for a week (polite, non-nagging — `lib/pwa.ts` cooldown policy).

### Standalone mode

When running installed (standalone), routing, auth, the map, voice search,
Copilot, saved searches and both dashboards behave exactly as in the browser.
The map keeps URL-syncing viewport/radius/destination, so **deep links and
shared map URLs restore the exact view inside the installed app**.

---

## Service worker strategy

`sw.js` keeps its original **push** handlers untouched and adds a deliberately
conservative cache:

| Request | Strategy |
|---|---|
| `/api/*` (and any non-GET) | **never cached** — always network |
| Navigations | network-first → cached app shell offline |
| Static assets (js/css/img/fonts/manifest) | cache-first, only on HTTP 200 |
| Anything else | network (no interception) |

- Caches are **versioned** (`rentora-static-v1`); on activate, only older
  `rentora-static-*` caches are deleted — unrelated caches are never touched.
- **No private data is ever cached**: auth responses, admin/fraud evidence,
  landlord/tenant data and payment payloads all hit the network.
- The worker is registered on app start (secure context only — https or
  localhost) and again on push opt-in; the same scope returns the same
  registration, so there is no double registration.

### Update experience

The worker `skipWaiting()`s + `clients.claim()`s so a new deploy activates
promptly. When the page's controller changes after an update, Rentora shows a
bottom banner — **"A new version of Rentora is available" [Refresh] [Later]**.
"Later" is remembered for 24 h. The first controller change (initial install)
never shows the banner.

---

## Offline behavior (P0 shell + P1 search)

No fake data, ever. When the connection drops:

- A slim amber banner appears ("You're offline — some features may be
  unavailable") while already-loaded UI stays visible.
- **P1 — offline search**: the Rooms page serves from the **IndexedDB cache**
  of PUBLIC listings (24 h TTL), re-filtered client-side (query/area/budget/
  type/gender/verified/amenities/sort), and shows a pill —
  "📡 showing N cached of M (offline)". Room details cache for 7 days.
- Actions made offline (wishlist toggles) are queued and replayed on reconnect.
- The cached app shell keeps the shell navigable; live data (map pins,
  bookings, chat) still requires a connection.
- Banners respect `env(safe-area-inset-*)` for iOS standalone.

**Cache policy recap** — only PUBLIC room list/detail data is ever cached. The
IndexedDB stores (`rentora-offline`) hold exactly two kinds of documents
(room lists, room details) plus the offline action queue. Auth responses,
admin/fraud evidence, payment payloads and personalized API responses are
never written to any cache.

---

## Security review

- Manifest is served as static JSON — no injection surface; `start_url` is
  root, no open redirect.
- Cache scope is limited to same-origin static assets; API traffic never
  cached (no stale auth/admin/fraud/payment data).
- Tokens stay in memory/localStorage exactly as before — the PWA adds no new
  storage of credentials.
- Service worker scope is root (`/sw.js`) with no third-party resources.
- `npm audit` / security CI unchanged and green.

---

## Testing & validation

- **Unit tests** (28 new across `pwa.test.ts`, `offlineDb.test.ts`,
  `backgroundSync.test.ts`): dismissal cooldowns, standalone detection,
  manifest validation, offline cache keys/TTL/filtering, queue replay +
  retry, periodic-sync registration. **230 frontend tests total.**
- **CI** (`scripts/validate-pwa.mjs`, run in the Frontend job after `npm run
  build`): validates the *built* manifest JSON, required fields, icon files
  with real PNG dimensions (192/512 + maskable), and that `sw.js` shipped.
- Full suites: `npx vitest run` (frontend), `python manage.py test` (backend),
  `npx tsc --noEmit`, eslint + prettier, `npm run build`.

---

## Background sync (P1)

Offline actions (wishlist toggle, saved-search check) are queued in IndexedDB
and replayed when the connection returns, through three redundant paths:

1. **Background Sync API** — `registration.sync.register("rentora-replay")`;
   the service worker's `sync` handler posts `rentora-replay` to open clients.
2. **`online` event** — universal fallback.
3. **`visibilitychange`** — replay when the tab becomes visible while online.

Failed replays are re-queued (never dropped silently). Only idempotent-ish
user actions are queued — never auth or payment operations.

## Periodic Background Sync (P1, feasible subset)

Research (2026): `registration.periodicSync` is **Chromium-only** (Chrome/Edge
80+, Android), requires an **installed** PWA + the `periodic-background-sync`
permission, and the browser schedules runs (site-engagement gated; `minInterval`
is a hint). **Notification Triggers API is not shipped in any browser** (it was
abandoned in Chromium) — documented as future scope.

Implementation: when the app is installed (standalone), `requestPeriodicRefresh`
registers a daily `rentora-refresh` tag; the SW's `periodicsync` handler asks
the app to refresh the PUBLIC cached listings so the offline cache never rots.
Everywhere else it degrades silently (`unsupported` / `denied` / no-op).

## Splash screens & dark icon

- **Apple splash screens** — 11 device-matched `apple-touch-startup-image` PNGs
  (640×1136 → 2048×2732, full-bleed brand gradient + centered house icon),
  linked from `index.html` with media queries.
- **Dark maskable icon** — `maskable-dark-512.png` (dark gray-800→900 gradient,
  white house) declared in the manifest alongside the light maskable icon.
  Manifest `theme_color` cannot be theme-aware (browser limitation), so dark
  home screens may still show the light splash.
- **iOS install hint** — Safari has no `beforeinstallprompt`, so a one-time,
  dismissible "Add to Home Screen" hint card appears on iOS instead of the
  navbar button.

## Lighthouse audit (prod build, Aug 2026)

| Category | Score | Notes |
|---|---|---|
| Performance | **84** | SPA first paint (client-rendered shell); FCP/LCP gated by JS + the map chunk |
| Accessibility | **93** | a11y tree + focus states verified |
| Best practices | **96** | |
| SEO | **82** | `robots.txt` added; SPA anchors not crawlable without SSR (documented) |

Lighthouse 12+ dropped the `pwa` category; installability is instead enforced
by `scripts/validate-pwa.mjs` in CI and the browser's own install prompt.
Improving the FCP/LCP (SSR/prerender or an app-shell skeleton) is tracked as a
Phase 16 performance item.

## Browser support

| Platform | Install | Notes |
|---|---|---|
| Chrome (desktop) | ✅ | full install prompt |
| Edge (desktop) | ✅ | full install prompt |
| Android Chrome/Edge | ✅ | install prompt + shortcuts |
| iOS Safari/iPadOS | ⚠️ | Add to Home Screen (no `beforeinstallprompt`; apple meta + icons cover it) |
| Firefox | ❌ | no install prompt API; PWA still runs as a normal site |

---

## Known limitations

- Offline search covers PUBLIC listings only (by design — private data is never
  cached); saved-search matching, chat and payments require a connection.
- Periodic Background Sync only runs in Chromium, on installed apps, and is
  scheduled by the browser (site-engagement gated) — not guaranteed daily.
- Notification Triggers API: not shipped in any browser → future scope.
- Shortcuts are not supported on iOS.
- The `theme_color` is the light brand; dark-mode installs still use the
  light-theme splash (browser limitation — the manifest cannot be theme-aware).
- SEO: SPA anchors are not crawlable without SSR/prerender (Lighthouse
  `crawlable-anchors`); tracked for Phase 16.
