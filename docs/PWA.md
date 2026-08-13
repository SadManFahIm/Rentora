# 📱 Progressive Web App (Phase 12 P0)

Rentora is installable as a native-feeling app on desktop (Chrome/Edge) and
mobile (Android Chrome/Edge, iOS Safari) — without a separate mobile codebase.
This document describes the P0 foundation: **manifest → icons → install UX →
standalone → deep links → security → performance**.

> **Scope note (P0):** installability does not require a service worker, so P0
> deliberately ships a *conservative* static-asset cache only. Full offline
> search, background sync and cached saved-searches are Phase 12 P1.

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
| `frontend/index.html` | Manifest link, theme-color, apple-mobile-web-app-* meta, viewport-fit |
| `frontend/public/sw.js` | Push + conservative static caching, versioned, self-cleaning |
| `frontend/src/lib/pwa.ts` | Pure policy helpers (dismiss cooldowns, standalone, manifest validation) |
| `frontend/src/hooks/usePwaInstall.ts` | `beforeinstallprompt` lifecycle + native prompt |
| `frontend/src/hooks/usePwaUpdate.ts` | "New version available" Refresh/Later detection |
| `frontend/src/hooks/useOnline.ts` | Offline state |
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

## Offline behavior

No fake data, ever. When the connection drops, a slim amber banner appears
("You're offline — some features may be unavailable") while already-loaded UI
stays visible. The cached app shell keeps the shell itself navigable; live
data (search, map pins, bookings) requires a connection. Banners respect
`env(safe-area-inset-*)` for iOS standalone.

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

- **Unit tests** (`src/lib/pwa.test.ts`, 11 tests): dismissal cooldowns,
  standalone detection, manifest validation, manifest fetch.
- **CI** (`scripts/validate-pwa.mjs`, run in the Frontend job after `npm run
  build`): validates the *built* manifest JSON, required fields, icon files
  with real PNG dimensions (192/512 + maskable), and that `sw.js` shipped.
- Full suites: `npx vitest run` (frontend), `python manage.py test` (backend),
  `npx tsc --noEmit`, eslint + prettier, `npm run build`.

---

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

- Offline is shell-only in P0 (no offline search/listing cache) — Phase 12 P1.
- Shortcuts are not supported on iOS.
- The `theme_color` is the light brand; dark-mode installs still use the
  light-theme splash (browser limitation — the manifest cannot be theme-aware).
