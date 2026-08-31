# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/) and
[Semantic Versioning](https://semver.org/). Change lines come from PR titles
(Conventional Commits). The project ships one feature phase per day.

## [Unreleased]

## 2026-08-31

### Phase 19.3 — AI Listing Autopilot
- Weekly Celery analyzer (`listing_autopilot`) mints typed, reviewable proposals (TITLE/DESCRIPTION/AMENITY/PHOTO/PRICE/RENEWAL) over eligible listings; landlord approves/rejects individually or bulk through `/api/v1/autopilot/*` (owner-only, audited).
- Deterministic analysis on top of the Phase 19.1/12.10/14 engines (LLM rewording limited to grounded title/description drafts); per-field `stale_checks` so sibling proposals stay independently applicable after apply.
- Idempotency throughout: one analysis per (room, week), no unresolved duplicate proposal per (room, type), replay-safe apply, per-room transaction + failure isolation, one batched notification per landlord.
- Frontend AutopilotPanel in Dashboard Insights (landlord-only); seeder registers flag `ai.listing_autopilot` (off by default) in the Phase 18 registries.

## 2026-08-30

### Workflow, docs & security
- `docs(workflow)` — Team Workflow section upgraded (branching / PR gates / pre-commit / environments / release cadence); CLAUDE.md conventions aligned.
- `docs(SECURITY.md)` — professional security policy: layered model, CVSS severity, coordinated disclosure, threat model (incl. AI-tool abuse & marketplace scams), secret handling, incident response, data protection, audit checklist.
- `docs(README)` — screenshot gallery extended to phases 15–19.2 (79 shots, light+dark, desktop+mobile) with per-phase detail blocks.

### Fixes
- `fix(analytics)` — strip doubled `/api/v1` prefix and map snake_case summary payload so the Analytics tab / market report render (was 404 + error-boundary crash).
- `fix(rental-agent)` — move mount-resume effect after `loadConversation` (TDZ crash blanked the Phase 19.2 panel).

### Tooling
- `chore(docs)` — idempotent demo-data seeder (`backend/scripts/seed_screenshots.py`) + combined phase 15–19.2 screenshot runner (`frontend/scripts/capture_phase15_19_shots.mjs`).
- `style(scripts)` — Prettier-format capture scripts (CI format gate).

## 2026-08-29

### Phase 19.2 — AI Rental Agent
- Tenant-facing agentic chat — `rental_agent` app (6 grounded tools, Bengali-first, self-consent bookmark proposals, sibling dedupe).
- SDK hardening: depth-truncation fix (4→8) and Bangla persistence limit fix (200k) with regression tests.

### Phase 19.1 — Property Intelligence Score
- Composite, explainable 0–100 score over six existing signals; versioned, cached, auditable.

### Phase 19.0 — Agent SDK
- Guarded agent kernel: registry, bounded session loop, server-side tool permission layer, staff/admin proposal lifecycle, provider+prompt+telemetry integration (Phase 18).

## 2026-08-26 → 2026-08-28

### Phase 18.x — AI Intelligence Foundation
- 18.1 — provider registry + execution telemetry + health/cost monitoring + admin API.
- 18.2 — prompt registry (versioned templates) + feature-flag integration + `register_ai_features`.
- 18.3 — evaluation framework: metrics, golden datasets, 26 evaluators, async runs, regression detection.
- 18.4 — intelligence dashboard + configurable alert rules with anti-noise lifecycle; admin UI (Dashboard → AI).

## Earlier phases (0–17)
See the [Delivery Roadmap](README.md#-delivery-roadmap) for the full phase history:
prototype → Django/DRF backend → real-time chat → payments (SSLCommerz/bKash) →
recommendation engine → roommate matching → fraud detection → map framework →
PWA → trust & safety v2 (KYC, chat safety, disputes) → reach (SMS OTP, WhatsApp) →
AI v3 vision & content → monetization 2.0 → hardening & scale → graph & deep trust.