# Phase 14 — AI v3: Vision & Content AI

Phase 14 is the **vision layer** of Rentora's AI stack: the platform now
"looks at" listing photos. Three features ship:

1. **AI photo → description** — draft a title + description from a listing's
   actual photos.
2. **Auto amenity tagging** — suggest amenity tags (furnished, AC, WiFi …)
   from photo evidence.
3. **AI image search** — upload any room photo and find listings that look
   like it.

Scope notes up front (honest):

- **This is statistical pixel vision, not object recognition.** The built-in
  core analyzes lighting, tone, colour and composition — it can say *"bright,
  airy, warm wood and beige tones"*, but it **cannot say "there is a double
  bed"**. Object-level amenity tags are only possible through a configured
  `http` vision gateway (external model API). Every response carries a `note`
  that says so.
- **Suggested tags are never auto-applied.** The landlord always reviews and
  clicks **Apply tags** — the platform suggests, the human decides.
- **External calls are opt-in.** `VISION_PROVIDER=heuristic` (default) needs
  no gateway and no secrets. `VISION_PROVIDER=http` + `VISION_GATEWAY_URL` +
  `VISION_GATEWAY_API_KEY` enables a real vision model; if the gateway fails,
  the system **gracefully falls back** to the heuristic core instead of
  failing.
- **Image search is look-alike search.** It ranks listings by perceptual
  similarity (phash + colour histogram + brightness) — a photo of a blue
  living room finds *other light-blue, bright rooms*, it does not identify
  the exact building.

## What ships

### 1. Photo intelligence core (`rooms/vision.py`)

- **`fingerprint_image(source)`** — Pillow-only image fingerprint: pHash
  (perceptual hash, 64-bit, same family as the existing duplicate-photo
  detector), a 64-bucket colour histogram (4 levels × 3 channels), brightness,
  colourfulness, and a 3-colour palette with human-readable names.
- **`listing_photo_profiles(room)`** — fingerprints up to 5 of the room's
  `RoomImage` photos.
- **`observations_from_profiles()`** — deterministic, confidence-scored
  observations about lighting (well-lit / dim), tone (light / warm / cool /
  colourful / neutral), décor (wood / green plants) and composition (depth /
  openness), derived **only from the pixel statistics**.
- **`heuristic_caption()`** — a composed caption: *"Photos show a bright,
  airy space with warm wood and beige tones."* Composed from the same
  statistics — never invented.
- **`_gateway_analyze()`** — the optional `http` provider. Sends the primary
  photo to `VISION_GATEWAY_URL` (JSON: `{image_url, prompt}`), strictly
  parses the reply (caption, observations, amenities) and **falls back to the
  heuristic core** on any error.
- **`analyze_listing(room)`** — runs the heuristic core, upgrades it with the
  gateway when configured. Returns caption, observations, suggested amenities,
  palette, provider name and the honesty note.
- **`image_search(query_bytes)`** — fingerprints the query photo and scores
  every listing photo: **50% pHash similarity + 25% histogram intersection +
  25% brightness closeness**. Listings below 35/100 are dropped; results carry
  the score and the human-readable reasons ("Similar composition", "Bright
  and airy").

### 2. Photo intelligence API (`rooms` app)

| Method | Endpoint | Auth | Description |
| ------ | -------- | ---- | ----------- |
| POST   | `/api/v1/rooms/<id>/vision/analyze/` | Owner or admin | Run + store photo intelligence for a listing |
| GET    | `/api/v1/rooms/<id>/vision/` | Owner or admin | The stored analysis (404 before first run) |
| POST   | `/api/v1/rooms/<id>/vision/description/` | Owner or admin | AI draft (title + description + tags) from the photos |
| POST   | `/api/v1/rooms/vision/search/` | Public (throttled) | Upload a photo → look-alike listings with match scores |

- Results are stored in a new **`RoomVisionAnalysis`** model (OneToOne to
  Room): provider, caption, observations, suggested_amenities, palette,
  photo_profiles, timestamps — so "Analyze photos" is a one-time cost and
  `GET /vision/` serves the cached analysis.
- `vision_analyze` / `vision_analysis` / `vision_description` are owner-or-admin
  (staff users allowed, like the price-recommendation flow).
- `vision_search` is **public** (anyone can search by photo), but throttled
  to **30 requests/minute** per client.
- Empty-photo listings → 422 on analyze; unreadable uploads → 400 on search;
  `VISION_ENABLED=False` → 503.
- 27 new tests (`rooms/test_vision.py`): fingerprint determinism, palette
  naming, observation correctness against synthetic solid-colour images,
  gateway fallback, permission matrix (owner / other landlord / admin), the
  public search contract and throttling.

### 3. Frontend

- **`VisionCard`** (landlord dashboard → My Listings) — per-listing photo
  intelligence panel: **Analyze photos** → caption, dominant-colour palette
  swatches, evidence observations, suggested tags with an **Apply tags**
  button (PATCHes the listing's amenities, review-first), and **AI draft from
  photos** → copy-ready title + description. Every panel shows the honesty
  note.
- **Image search** (`/rooms`) — a **Image search** button next to the
  grid/list toggle opens the upload dialog (preview included). Results render
  in the normal grid, each card carrying a **`88% match`** badge with the
  reasons in its tooltip, plus a "N visual matches for your photo" bar with a
  Clear button.
- **i18n** — all new strings in English + বাংলা (`vision` namespace).
- 9 new frontend tests (`visionService.test.ts` 5, `VisionCard.test.tsx` 4);
  `tsc --noEmit`, ESLint (0 errors) and `vite build` clean.

## Configuration

| Setting (`base.py`, `os.getenv`) | Default | Purpose |
| -------------------------------- | ------- | ------- |
| `VISION_ENABLED` | `True` | Master switch; off → vision endpoints 503 |
| `VISION_PROVIDER` | `heuristic` | `heuristic` (built-in, offline) or `http` (gateway) |
| `VISION_GATEWAY_URL` / `VISION_GATEWAY_API_KEY` / `VISION_GATEWAY_MODEL` | `""` | HTTP provider connection (optional) |
| `VISION_SEARCH_TOP_K` | `8` | Max image-search matches per query |

Throttle scope `"vision": "30/minute"` (DRF `ScopedRateThrottle`, applied
manually on the public search action).

Backend env vars are documented in `backend/.env.example`.

## Tests

- Backend: **716 tests pass** (was 689; +27 new in `rooms.test_vision`).
- Frontend: **342 tests pass** (was 333; +9 new).
- Migration: `rooms/0007_roomvisionanalysis.py` (created + applied to the
  dev DB).

## Screenshots

- `docs/screenshots/phase14-vision-panel.png` — the photo-intelligence panel
  on a listing in the landlord dashboard (analysis + AI draft).
- `docs/screenshots/phase14-image-search-dialog.png` — the image search
  dialog with a chosen photo preview.
- `docs/screenshots/phase14-image-search-results.png` — look-alike results
  with match badges.

Captured by `frontend/scripts/capture_phase14_shots.mjs` (Playwright, real
stack): logs in as the `rahim.hossain` demo landlord for the dashboard shot,
then captures the public image-search flow (the query photo is a real listing
photo re-used from the grid, so matches are guaranteed).

## What this phase does NOT do (deferred)

- **True object recognition** (furniture/AC/WiFi detection) — that requires
  `VISION_PROVIDER=http` with a real vision model; the provider contract and
  graceful fallback ship now, credentials do not.
- **Auto-applying suggested tags** — deliberately deferred: suggestions are
  always reviewed by the landlord before any change.
- **Semantic search by description** — image search ranks by pixel
  similarity; caption-based semantics are the existing smart-search domain.
