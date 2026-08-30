# Tier-4 Upgrades — AI Tools, Comparison, Forecasting & Platform Hardening

Part of the **12.9** delivery slice (after Phase 12 Trust & Safety V2, Tier-1/2/3
quick wins). Everything here reuses the existing Django REST API, the floating
Copilot surface, the notification stack and the embedding pipeline — nothing
was rewritten.

## What shipped

| Feature | Where | Backed by |
| ------- | ----- | --------- |
| 🤝 AI Rental Advisor | Copilot → AI Tools | `POST /api/v1/copilot/advisor/` — live listing stats |
| 💬 AI Negotiation Assistant | Room modal → **Draft negotiation** | `POST /api/v1/copilot/negotiate/` — comparable listings |
| 📄 AI Rental Agreement Checker | Copilot → AI Tools | `POST /api/v1/copilot/agreement-check/` — deterministic rules |
| 🏠 Landlord Copilot | Landlord dashboard widget | `POST /api/v1/copilot/landlord/` — owned listing insights |
| 📊 AI Property Comparison | Rooms page → compare drawer | `GET /api/v1/rooms/compare/?ids=…` |
| 📈 Demand Forecasting | Analytics + alerts + landlord insight | `GET /api/v1/analytics/forecast/` |
| 🔔 Smart AI Alerts | Notifications inbox re-ranked | `GET /api/v1/notifications/smart/` |
| 🧠 Hosted neural embeddings | `SEMANTIC_EMBEDDING_PROVIDER=hosted` | Remote HF endpoint, lite fallback |
| 🪪 Automated KYC pre-verification | `USERS_KYC_PROVIDER` pluggable | Deterministic pre-screen, manual fallback |
| 🧪 Browser-level Playwright E2E | `frontend/e2e` + CI job | Real Chromium against the dev stack |

## Design notes

- **Grounded by construction.** The advisor, negotiator and landlord copilot
  only cite figures computed from the live `Room` table (median rent per area,
  comparable listings). They never return invented prices or availability.
- **Deterministic where it matters.** The agreement checker uses explicit
  clause patterns (advance payment, refund terms, notice period, deposit
  return) rather than an opaque model — every finding is explainable.
- **Transparent ranking.** Smart alerts attach a `priority` (0–100) and a
  plain-language `reason` to every notification so users (and auditors) can
  see *why* something rose to the top.
- **Safe fallbacks everywhere.** Hosted embeddings fall back to local lite
  mode on any network/model error; the KYC provider only auto-approves clear
  passes and otherwise reuses the existing manual admin review workflow.
- **Cheap by default.** Forecasting is a lightweight moving-average/trend
  model over saved-search and booking signals — no external service, no
  queue, no added latency on the hot path.

## Configuration

| Setting | Default | Meaning |
| ------- | ------- | ------- |
| `SEMANTIC_EMBEDDING_PROVIDER` | `auto` | `auto` / `neural` / `lite` / `hosted` |
| `SEMANTIC_EMBEDDING_HOSTED_URL` | — | Remote embeddings endpoint (used only when `hosted`) |
| `USERS_KYC_PROVIDER` | `manual` | `manual` / `auto` / `mock` (mock is test-only) |
| `KYC_AUTO_APPROVE_ON_PASS` | `False` | Auto-approve clear passes (start `False` in prod) |

## Testing

- Backend: `test_advisor.py`, `test_compare.py`, `test_forecast.py`,
  `test_smart_alerts.py`, `test_hosted_embeddings.py`, `test_kyc_provider.py`
  (26 new tests; the full backend suite is 651).
- Frontend: service-layer tests for `tier4Service`; the full Vitest suite is
  320.
- Browser: `npm run test:e2e` — Playwright boots the dev server and runs
  `e2e/smoke.spec.ts` (render, search, Copilot listing Q&A). CI runs it as a
  dedicated job with a Chromium install.

## Screenshots

See the [phase gallery](../README.md#-screenshots) — `phase12.9-*.png`
(advisor, compare, landlord copilot, smart alerts) and `phase12.8-*.png`
(RAG listing Q&A, EN⇄BN toggle, completed-bookings chip).
