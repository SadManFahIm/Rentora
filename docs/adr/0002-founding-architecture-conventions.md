# ADR-0002: Founding architecture conventions

- **Status:** accepted
- **Date:** 2026-08-30
- **Context:** These are the platform's stable foundation choices. Recording
  them makes future decisions (ADR-0003+) cheaper to reason about.

## Decisions

| Area | Decision |
|------|----------|
| Repo shape | Monorepo: `frontend/` (SPA), `backend/` (Django), `docs/`, `scripts/`. |
| Backend | Django 5 + DRF, PostgreSQL 16 + Redis; Python 3.12 (`.python-version`). |
| Frontend | React + Vite, TypeScript **strict**, Tailwind v4, shadcn/ui, Zustand. |
| API | Everything under `/api/v1/`; DRF + JWT; OpenAPI contract + generated TS types. |
| Real-time | Django Channels + WebSocket (chat, notifications). |
| AI | Guarded Agent SDK (Phase 19.0): server-side tool permissions, proposals for state changes, provider/prompt/telemetry registries (Phase 18). |
| Payments | SSLCommerz + bKash with idempotent ledger + webhook audit. |
| Delivery | One phase/day, Conventional Commits, PR against `main`, 13 CI gates, screenshots per UI change. |
| Style | ruff (backend) + ESLint/Prettier 3.9.x (frontend), enforced at commit and CI. |

## Consequences

- New Django work adds a snake_case app under `backend/` (e.g. `rental_agent`)
  with matching frontend modules; the conventions above are expected to change
  only through a new ADR.