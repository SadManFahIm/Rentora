# Screenshot workflow & inventory

Every README screenshot lives in this folder as a flat `*.png` and is
referenced from the [🖼️ Screenshots](../../README.md#-screenshots) section
(phase-wise gallery table + detailed blocks).

## How screenshots are captured

Tier-4+ captures are automated with Playwright — `frontend/scripts/capture_tier4_shots.mjs`,
`capture_tier5_shots.mjs` (log in as `admin.demo`),
`capture_phase13_shots.mjs` (public pages, no login) and
`capture_phase14_shots.mjs` (logs in as the `rahim.hossain` demo landlord for
the vision panel, then captures the public image-search flow) run against the
dev stack (backend :8000, frontend :3001) and capture real UI state. Older
captures were done manually; the workflow below still applies to both:

1. **Run the stack** — `cd backend && venv/Scripts/python.exe manage.py
   runserver` and `cd frontend && npm run dev` (see the repo README
   [Getting Started](../../README.md#-getting-started)).
2. **Seed safe demo data** — `cd backend && venv/Scripts/python.exe
   manage.py seed_phase12_demo` (if present) or the standard
   `seed_rooms`/fixtures. **Never** use real user data.
3. **Drive the flow in a browser** (Chrome dev tools, 1440px desktop and
   390px mobile where the feature is mobile-first): log in as the right
   demo user, walk the flow, and capture the screen.
4. **Name it phase-first** — `phase<NN>-<feature>.png`, or the feature
   itself for the well-known ones (`trust-center.png`, `audit-trail.png`,
   `report-block.png`, …). Keep the existing names when extending a
   feature (overwrite) so README links never rot.
5. **Sanity check before committing** — no real NIDs, no personal data, no
   production secrets, no private URLs. Dark-mode variants get a
   `-dark` suffix.

## Phase inventory (64 files)

| Phase | Files |
| ----- | ----- |
| 4 | `voice-search.png` |
| 5 | `deposit-protection.png` |
| 6 | `listing-quality.png`, `price-anomaly.png`, `pricing-suggestion.png` |
| 7 | `map-view*.png`, `map-intel-*.png`, `map-ux-*.png` |
| 9 | `kyc-sla.png`, `kyc-trend-chart.png`, `kyc-admin-panel.png`, `kyc-upload.png` |
| 10 | `phase10-*.png`, `saved-search-match.png` |
| 11 | `phase11-ai-search.png`, `copilot.png`, `duplicate-image-fraud.png`, `fraud-admin.png`, `fraud-detection.png`, `listing-quality.png` |
| 12 | `tenant-kyc-*.png`, `verified-tenant-badge.png`, `report-block.png`, `chat-safety-feed.png`, `moderation-*.png`, `dispute-admin.png`, `trust-center.png`, `audit-trail.png`, `verified-badge-dark.png`, `kyc-mobile.png` |
| 12.6–12.8 | `phase12.8-copilot-listing-qa.png` (RAG listing Q&A), `phase12.8-lang-toggle.png` (EN⇄BN), `phase12.8-completed-bookings.png` (trust chip) |
| 12.9 | `phase12.9-ai-tools-advisor.png` (AI advisor), `phase12.9-compare.png` (property comparison), `phase12.9-landlord-copilot.png`, `phase12.9-smart-alerts.png` |
| 12.10 | `tier5-price-recommendation.png` (per-listing price advice), `tier5-ai-draft.png` (listing form AI draft), `tier5-copilot-photos.png` (Copilot photo answer) |
| 13 | `phase13-area-page.png` (area SEO landing page), `phase13-whatsapp-share.png` (WhatsApp share), `phase13-sms-login.png` (phone sign-in) |
| 14 | `phase14-vision-panel.png` (photo intelligence on a listing), `phase14-image-search-dialog.png` (image search upload), `phase14-image-search-results.png` (look-alike results with match badges) |
