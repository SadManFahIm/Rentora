# Tier-1 Dependency Bump Audit

*Part of the Tier-1 Quick Wins batch — run `pip list --outdated` (backend) and
`npm outdated` (frontend) on 2026-08-15.*

## Scope

This audit covers the two dependency sets that ship with the repo:

- `backend/requirements.txt` — exact pins, Python 3.12 venv.
- `frontend/package.json` + `package-lock.json` — caret ranges.

Policy: bump **patch/minor within the same major** when the package is a
direct dependency and semver-compatible; **hold majors** for the next
dedicated upgrade cycle (they deserve migration work, not a drive-by bump).
Every applied bump is verified by the full test suites (512 backend, 312
frontend) and the production build.

## Backend — applied (safe)

| Package | From | To | Notes |
|---|---|---|---|
| django-allauth | 65.18.0 | 65.19.1 | patch; auth wiring covered by users tests |
| sentry-sdk | 2.66.1 | 2.68.0 | minor; no-op without SENTRY_DSN |
| redis | 8.0.1 | 8.1.0 | minor; only used when CHANNELS_BACKEND=redis |
| sqlparse | 0.5.5 | 0.6.0 | minor; Django 5.2-compatible |
| numpy | 2.4.6 | 2.5.2 | patch-level within 2.x; scikit-learn 1.9 + pandas 2.3 verified |
| cbor2 | 6.1.3 | 6.1.4 | patch |
| cffi | 2.1.0 | 2.1.1 | patch |
| charset-normalizer | 3.4.9 | 3.5.1 | patch/minor |
| ruff | 0.16.1 | 0.16.3 | patch; dev tool |
| coverage | 7.15.3 | 7.15.4 | patch; dev tool |
| pyOpenSSL | 26.3.0 | 26.4.0 | patch; aligned to the pinned version |
| pandas / scipy | — | — | rebuilt alongside numpy, versions unchanged |

## Backend — held for the next cycle

| Package | Current | Latest | Why held |
|---|---|---|---|
| Django | 5.2.16 | 6.1 | **Major.** 5.2 is LTS; 6.x upgrade needs its own release with migration + breaking-change review |
| djangorestframework | 3.17.1 | 3.18.0 | Minor but behavior-relevant (serializer/viewset defaults); review separately |
| websockets | 16.1.1 | 17.0.1 | Major; Channels/Daphne compatibility must be re-verified |
| pyee | 13.0.1 | 14.0.0 | Major; pulled by playwright (tool) |

## Frontend — applied (caret ranges, pulled by `npm install`)

| Package | From | To | Notes |
|---|---|---|---|
| @hookform/resolvers | 5.4.0 | 5.9.0 | minor; Zod resolver covered by form tests |
| @radix-ui/react-dialog / -select / -slot | 1.1.20 / 2.3.4 / 1.3.0 | 1.1.23 / 2.3.7 / 1.3.3 | patches |
| @sentry/react | 10.69.0 | 10.70.0 | minor |
| @testing-library/jest-dom / user-event | 7.0.0 / 14.6.3 | 7.0.1 / 14.6.4 | patches (dev) |
| @zxcvbn-ts/core | 4.1.2 | 4.2.0 | minor |
| axios | 1.18.1 | 1.19.0 | minor |
| eslint / eslint-plugin-react-refresh | 10.8.0 / 0.5.3 | 10.8.1 / 0.5.4 | patches (dev) |
| lucide-react | 1.25.0 | 1.31.0 | minor; icon set additive |
| maplibre-gl | 6.2.0 | 6.3.0 | minor; map tests + build verified |
| motion | 13.0.0 | 13.1.0 | minor |
| react-hook-form | 7.82.0 | 7.85.0 | minor |
| sonner | 2.0.7 | 2.0.8 | patch |
| typescript-eslint | 8.66.0 | 8.67.0 | minor (dev) |
| zustand | 5.0.14 | 5.0.15 | patch |

## Frontend — held for the next cycle

| Package | Current | Latest | Why held |
|---|---|---|---|
| react / react-dom | 18.3.1 | 19.2.8 | **Major.** React 19 upgrade (refs, Suspense, types) deserves a dedicated branch |
| @types/react / @types/react-dom | 18.3.31 / 18.3.7 | 19.x | must move together with React 19 |
| vite | 6.4.3 | 8.2.1 | **Major** (two majors); plugin compat + build config re-validation |
| @vitejs/plugin-react | 4.7.0 | 6.0.5 | major; move with Vite |
| vite-tsconfig-paths | 5.1.4 | 6.1.1 | major |
| typescript | 5.9.3 | 7.0.2 | **Major** (two majors); large toolchain review |
| react-router-dom | 6.30.4 | 7.18.2 | **Major.** v7 route/loader migration is a project of its own |

## Vulnerabilities

- `npm audit` reports **0 high / 0 critical**; **2 moderate** remain, both in
  `react-router` / `react-router-dom` 6.x (CVE-2025-68470-related, fixed in
  the 7.x line). They are held deliberately: react-router-dom 7 is a major
  upgrade scheduled for its own migration cycle (see the held table).
  `npm audit fix` would force that major, so it is **not** run.
- Backend `pip` shows no known-vulnerable direct dependencies.

## How to re-run

```bash
# Backend
cd backend && venv/Scripts/python.exe -m pip list --outdated --format=columns

# Frontend
cd frontend && npm outdated && npm audit
```
