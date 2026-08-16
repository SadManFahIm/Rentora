# Screenshot workflow & inventory

Every README screenshot lives in this folder as a flat `*.png` and is
referenced from the [🖼️ Screenshots](../../README.md#-screenshots) section
(phase-wise gallery table + detailed blocks).

## How screenshots are captured

Rentora has no screenshot automation yet — captures are done manually with
real app state, then committed:

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

## Phase inventory (50 files)

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
| 12.6–12.8 | *not yet captured* — Tier-1/2/3 upgrades (chat edit/delete, analytics funnel, RAG Copilot listing Q&A, EN⇄BN toggle, completed-bookings chips) are live in the app; capture with the workflow above and add to the gallery table |
