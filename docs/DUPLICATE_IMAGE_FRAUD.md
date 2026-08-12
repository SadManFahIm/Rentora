# 🖼️ Cross-Listing Duplicate Image Fraud Detection

Detects the same (or visually near-identical) photo re-used across **different
listings** — the classic scam-listing pattern — and feeds the result into the
existing fraud engine.

## Architecture

```text
Upload / existing image
        ↓
pHash (reuse rooms/image_search.py — 64-bit average hash, cached in RoomImageHash)
        ↓
hex-prefix pre-filter (no N×N full-table pass)
        ↓
Hamming distance ≤ IMAGE_DUPLICATE_THRESHOLD (default 8 bits)
        ↓
contextual severity → FraudSignal(duplicate_image) → FraudReport score
        ↓
fraud-aware search ranking + admin ops panel
```

### Reuse over rebuild

- Hashing is the **existing** `rooms.image_search` pipeline (Pillow average
  hash cached per image keyed by file mtime) — the duplicate detector calls it,
  it does not hash a second way.
- Comparison is over cached hex hashes with a 4-char prefix index, so a scan
  never does an N×N full-table pass.
- Other rooms' primary images are warmed (hashed + cached) lazily on first
  scan of a listing, capped (`WARM_CAP = 500`) so a cold catalogue can't cause
  a pathological run — steady state is cache-hits only.

### False-positive protection

- Images repeated **within one listing** are a gallery, never fraud.
- Same-owner duplicates (an agency or a property manager posting several rooms
  of one apartment) downgrade to **low** — a signal, not an accusation.
- Blank/solid-colour images hash degenerate (all-zero bits) and are skipped.
- Threshold and switch are configurable.

### Severity (contextual)

| Scenario | Severity |
| --- | --- |
| Same photo across 2 listings, different owners | Medium |
| Same owner only (agency/multi-room) | Low |
| 3+ distinct matches, **or** different owner **and** different area | High |

Evidence stored per signal: `matched_listing_ids`, `similarity` (1 − distance/64),
`same_owner`, `same_area`, `owner_id`.

## Integration

- **Fraud engine** — the detector is registered in `DETECTORS`
  (`fraud/services/detectors.py`) so it runs on room-create auto-scan, manual
  re-scan, and the daily catalogue scan; its score/severity feeds
  `FraudReport` and therefore the existing **fraud-aware search ranking**.
- **Admin ops panel** — Dashboard → Fraud Operations shows the signal with a
  message, similarity %, and clickable **matched listing** chips (#1023) that
  open the related listings for investigation.

## How admins should investigate

1. Compare the matched listings side by side.
2. Compare owners (same person? same agency?).
3. Compare locations (same property? different areas?).
4. Review other fraud signals on each listing.
5. Take moderation action per policy — a duplicate image is a **risk signal,
   not automatic proof of fraud**.

## Configuration

| Env / setting | Default | Meaning |
| --- | --- | --- |
| `DUPLICATE_IMAGE_FRAUD_ENABLED` | `True` | Master switch |
| `IMAGE_DUPLICATE_THRESHOLD` | `8` | Max differing Hamming bits (of 64) to count as "same" |
| `IMAGE_DUPLICATE_MIN_LISTINGS` | `2` | Platform size before the detector bothers |
| `WARM_CAP` (module) | 500 | Max other rooms' primaries warmed per scan |

## Tests

`fraud/test_duplicate_image.py` — same image across listings (medium), across
owner+area (high), same owner (low), distinct images clean, same-listing
gallery not flagged, flag disable, `run_scan` integration, multi-room dedupe,
warm-up of previously-unhashed listings.

## Limitations

- Detection is per-*primary*-image for warming; all images of the target are
  compared. A match is only found once both sides have been hashed (within one
  catalogue scan cycle).
- Average hashing tolerates resize/compression but not heavy crops/rotations.
- A deliberate scammer can defeat it with a new photo — this is one signal in
  a six-detector engine, not the whole story.
