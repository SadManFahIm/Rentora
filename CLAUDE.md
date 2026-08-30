# Rentora — AI-Powered Room Rental Platform (Bangladesh)

## Stack
- Frontend: React 18 → migrating to TypeScript + Vite + TailwindCSS v4
- Backend: Django 5 + DRF + PostgreSQL 16 + Redis (Phase 3+)
- Real-time: Django Channels + WebSocket (Phase 4)
- Payments: SSLCommerz + bKash (Phase 5)

## Project Structure
- frontend/ — React SPA
- backend/ — Django project (coming Phase 3)
- docs/ — Documentation

## Conventions
- TypeScript strict mode for frontend
- Django apps: snake_case (rooms, bookings, chat, payments, ai_features)
- API prefix: /api/v1/
- Git branches: feature/phase-{N}-{feature-name}, fix/{slug}, docs/{slug}, chore/{slug}, refactor/{slug}; never commit directly to main
- Commit messages: Conventional Commits (<type>(<scope>): <summary>)
- Always generate full files, not diffs
- PR descriptions required for every merge (what/why, files, testing, screenshots)
- Pre-commit: husky + lint-staged (Prettier + ESLint on TS, ruff on Python); run tsc --noEmit before push
- CI must be fully green before merge (Vitest+build, Django tests, gitleaks, Playwright, contract/schema drift, npm audit, Lighthouse)

## Developer
- Name: Sadman Chowdhury Fahim
- Git email: faahimsadman@gmail.com
- Company: NeoNexor Software

## Commands
- Frontend: cd frontend && npm run dev
- Backend: cd backend && python manage.py runserver