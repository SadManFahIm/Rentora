# Contributing to Rentora

Thanks for helping build Rentora 🏠 — an AI-powered room-rental platform for
Bangladesh. Please read this before opening a branch or a PR.

- [Code of conduct](#code-of-conduct)
- [Local setup](#local-setup)
- [Project layout](#project-layout)
- [Development workflow](#development-workflow)
- [Coding standards](#coding-standards)
- [Testing](#testing)
- [Pull request checklist](#pull-request-checklist)

## Code of conduct

Be respectful. Rentora is a two-sided marketplace — experience harmless
experiments on your own copy, never on live users. No secrets (API keys,
passwords, payment credentials) may ever be committed.

## Local setup

Requirements: **Python 3.12** (see `.python-version`) and **Node 22**
(see `.nvmrc`).

```bash
make setup            # venv → pip install -r backend/requirements.txt → npm ci
make dev              # backend on :8000, frontend (Vite) on :3001
make seed             # idempotent demo data for the screenshot galleries
```

> The frontend Vite dev server runs on **:3001** — the process on `:3000` is a
> different app. Backend defaults to `:8000` with `runserver`.

Demo accounts (all password `demo12345`):
`rahim.hossain@rentora.com` (landlord) · `tenant.pending@rentora.com` ·
`admin@rentora.com`.

## Project layout

```
frontend/   React + TypeScript SPA (Vite, Tailwind v4, shadcn/ui, Zustand)
backend/    Django 5 + DRF monolith (apps under /api/v1/), PostgreSQL + Redis
docs/       phase specs, architecture, security, API reference
scripts/    repo-level tooling (backups, coverage, icons, PWA validation)
.github/    CI workflows, PR template, code owners, dependabot
```

New features land as a new Django app (snake_case, e.g. `rental_agent`) plus
the matching frontend modules (`services/`, `hooks/`, `components/`).

## Development workflow

1. **Branch** — never commit to `main` directly. Off a fresh upstream main:
   `feature/phase-<N>-<slug>` · `fix/<slug>` · `docs/<slug>` · `chore/<slug>` ·
   `refactor/<slug>`.
2. **Small, daily commits** — one phase per branch, merged within the day.
   Conventional Commits: `<type>(<scope>): <summary>` (`feat/fix/docs/chore/
   refactor/style/test`).
3. **PR against `main`** with the template (summary, what/why, files, testing,
   screenshots for UI). CI must be fully green before merge — Vitest + build +
   coverage, Django tests, gitleaks secret scan, Playwright, API contract +
   schema drift, npm audit, Lighthouse.
4. **Merge** — the authorized account squash-merges; never merge your own open
   PR.

## Coding standards

- Frontend: TypeScript **strict**; ESLint + Prettier (3.9.x) via
  husky + lint-staged on every commit; run `npx tsc --noEmit` before push.
- Backend: ruff (`backend/ && python -m ruff check .`); Django apps snake_case;
  API prefix `/api/v1/`; always generate full files, not diffs.
- Secrets: `.env*` files are gitignored and never committed; put anything
  secret in GitHub Actions secrets / environment variables.

Run the whole local gate with:

```bash
make check
```

## Testing

- Backend: `make test-backend` (Django test suite — several thousand tests).
- Frontend: `make test-frontend` (Vitest + coverage).
- E2E: Browser E2E (Playwright) and the fraud/payments/KYC suite run in CI.

## Pull request checklist

- [ ] Branch named per convention, off a fresh upstream `main`
- [ ] Description follows the PR template (what/why, files, testing, screenshots)
- [ ] `make check` passes locally
- [ ] CI is fully green (all 13 checks)
- [ ] No secrets in the diff (gitleaks runs in CI)
- [ ] Screenshots added for any UI change (into `docs/screenshots/`)