# 🏠 Rentora — AI-Powered Room Rental Platform

> Bangladesh's smartest room rental platform. Find verified, affordable rooms with AI-powered recommendations, real-time chat, secure payments, roommate matching, and fraud detection.

[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)](https://djangoproject.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6?logo=typescript)](https://typescriptlang.org)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![DRF](https://img.shields.io/badge/DRF-3.15-a30000?logo=django)](https://www.django-rest-framework.org/)
[![Tests](<https://img.shields.io/badge/tests-1777%20(1411%20BE%20%2B%20366%20FE)-success>)](https://github.com/SadmaFaahiim/Rentora/actions)
[![Coverage](https://img.shields.io/badge/coverage-BE%2060%25%20%E2%80%A2%20FE%2099%25-success)](https://github.com/SadmaFaahiim/Rentora/actions)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions)](https://github.com/SadmaFaahiim/Rentora/actions)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📚 Table of Contents

- [Product Overview](#-product-overview)
- [Changelog — Phase 19.2 · 19.1 · 19.0 · 18.4 · 18.3 · 18.2 · 18.1 · 17](#changelog)
- [What's New in v2.0](#changelog--whats-new-in-v20)
- [Delivery Roadmap](#-delivery-roadmap)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Quality Engineering](#-quality-engineering)
- [Getting Started](#-getting-started)
- [API Endpoints](#-api-endpoints)
- [Documentation](#documentation)
- [Security](#-security)
- [Passkeys / WebAuthn](#-passkeys--webauthn--shipped)
- [Progressive Web App](#-progressive-web-app--shipped)
- [Demo Users](#-demo-users)
- [Screenshots](#-screenshots)
- [Team Workflow](#-team-workflow)
- [Developer](#-developer)
- [License](#-license)

---

## 📋 Product Overview

|                     |                                                                                                                                                                                               |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Problem**         | Finding a trustworthy room in Dhaka is hard — listings are scattered, landlords are hard to verify, and scams are common.                                                                     |
| **Solution**        | One verified marketplace: AI-scanned listings, real-time landlord chat, secure gateway payments, roommate matching, and an ML-powered fraud engine that catches bad actors before tenants do. |
| **Target users**    | Tenants (students & young professionals) and landlords in Bangladesh.                                                                                                                         |
| **Differentiators** | Fraud-engineered trust layer, AI recommendations & fair-price insight, roommates (a growth hook competitors lack), and a monetized listing-tier system (Free → Featured → Premium).           |

---

## ✨ Product Preview

One platform, four surfaces — **browse smarter**, **trust the listings**, **sell faster**, **run on data**:

| Surface | What you see | Screenshot |
|---|---|---|
| 🗺️ **Intelligent Map** | AI map search ("উত্তরায় ১২ হাজারের মধ্যে furnished room"), metro commute scores, value-score pins, area intelligence & affordability | [`map-intel-ai-search.png`](docs/screenshots/map-intel-ai-search.png) |
| 🔍 **AI Smart Search** | Bangla/Banglish natural-language search with intent chips + semantic ranking | [`phase11-ai-search.png`](docs/screenshots/phase11-ai-search.png) |
| 🛡️ **Fraud Operations** | Auto-scanned listings, risk scores, admin review queue + duplicate-image detection | [`fraud-admin.png`](docs/screenshots/fraud-admin.png) |
| 🧑‍🤝‍🧑 **Roommate Matching** | Compatible flatmates by budget, area & lifestyle | [`roommates-matching.png`](docs/screenshots/roommates-matching.png) |
| 🛡️ **Trust & Safety** | Two-sided marketplace integrity — tenant KYC + verified-tenant badge, chat safety engine, report/block, photo & review moderation, disputes + deposit protection, admin Trust Center & audit trail | [`trust-center.png`](docs/screenshots/trust-center.png) |
| 📱 **Reach** | SMS OTP phone sign-in for the Bangladesh market, one-tap **Share on WhatsApp** with an AI listing summary, per-area SEO landing pages + sitemap, Lighthouse gate in CI | [`phase13-area-page.png`](docs/screenshots/phase13-area-page.png) |
| 👁️ **AI Vision** | **Photo intelligence** — analyze a listing's photos (caption, palette, observations), AI draft title + description from the actual photos, suggested amenity tags (review-then-apply), and **AI image search** ("upload a photo, find rooms that look like it") with match scores | [`phase14-vision-panel.png`](docs/screenshots/phase14-vision-panel.png) |

Full gallery (79 screenshots, light + dark, desktop + mobile) in [🖼️ Screenshots](#-screenshots). Live verification notes in [`docs/LIVE_VERIFICATION.md`](docs/LIVE_VERIFICATION.md).

---

## 🆕 Changelog

**Phase 19.2 — AI Rental Agent (tenant-facing agentic chat)**

- **Conversational rental agent** — a Bengali-first agent (বাংলা / Banglish / English) inside the Copilot widget that searches the live Dhaka catalogue, explains listings, estimates commutes, compares prices and can request a bookmark — every answer grounded in the platform's own tools, never invented
- **6 tools, 1 new app** (`rental_agent`) — `search` (grounded room cards + area median/peak/cheapest), `room_details` (card + property-intelligence badge), `commute` (map-intel estimate or honest `available:false`), `price_compare` (segment P10/P50/P90 + overpriced flag), `area_overview` (median + trend or honest no), `bookmark` (`STATE_CHANGING` proposal); all results flow through the one shared privacy-first `room_card` shape (28 public-only keys) rebuilt per message so the UI renders the stored ground truth
- **Dignified consent for the only side effect** — bookmarking needs human review: token-holding **self-consent** (the tenant's own turn is the authorization) moves PENDING → APPROVED, then applies once and **expires sibling PENDING bookmark proposals across all of that tenant's conversations** (one booking intent, no duplicates); the UI deliberately shows both stages ("await approval" → "applied") so the tenant stays in control
- **API** — `POST /api/v1/rental/chat/` (creates+continues conversations, async run with eager fallback), `GET /conversations/` + `GET /conversations/<pk>/` (enriched transcript with attached cards, proposals, suggestion chips, feature state), `GET /runs/<key>/` (poll), `POST /proposals/<key>/approve|reject/` (owner-only, concurrency-safe, TTL) — auth + 40/h throttle
- **Agent** — seeded via idempotent `register_rental_agent` command: flag `ai.rental_agent` (**disabled by default**), prompt `rentora.rental_agent` v1, agent `ai.rental_agent` (gpt-4o-mini, 6 tools, max_turns=6, max_tool_calls=20, max_tokens=4000, 60s); provider/prompt resolved through the Phase 18.1/18.2 registries
- **SDK hardening (shared)** — `_sanitized_outcome` depth limit raised 4 → 8 and dict/list caps 50 → 200 so deep structured tool results survive into persistence and context (was nulling room-card fields — a grounding hazard); `_persist_message` gained `limit=` and tool payloads persist at 200 K so বাংলা (6× via `ensure_ascii`) never truncates mid-JSON; +1 regression test
- **Frontend** — `rentalAgentService.ts` + `useRentalAgent` (send → poll run → reload enriched payload, honest errors, unmount-safe) + `RentalAgentPanel` (EN/BN examples, grounded cards opening the real RoomModal, amber "await approval" rows with Approve/Reject, suggestion chips, feature-off banner) as a new **Rental Agent** tab in the Copilot AI Tools, defaulted on open
- **Engineering** — 42 new `rental_agent` tests + 1 SDK regression (81 combined OK, adjacent suites 886 OK), ruff-clean, `manage.py check` clean, TS strict + ESLint + Prettier clean. See [`docs/phase-19-2-ai-rental-agent.md`](docs/phase-19-2-ai-rental-agent.md)

**Phase 19.1 — Property Intelligence Score**

- **Composite, explainable 0–100** — deterministic score on top of existing signals with zero new tables: listing quality (25), price competitiveness vs. segment market (20), metro/commute value (15), photo authenticity (15), verification + fraud severity (15), and 30-day demand (10); unavailable signals **redistribute their weight** over the live ones so missing data never inflates or punishes
- **Transparent by law** — every payload carries a per-component breakdown (`score`, `weight`, `effective_weight`, `contribution`, `availability`), confidence tier (`high/medium/low/none`) with reasons (availability, price sample size, freshness/staleness), strengths and rule-based suggestions (max 5, never LLM-invented), plus an explicit disclaimer ("not a valuation, fraud verdict, or guarantee")
- **Privacy by construction** — public output **never** includes internal fraud risk scores, detector names, graph/ring IDs, KYC or provenance; a staff-only detail endpoint — gated by `is_staff`/admin role and audited via `audit_log_access` — attaches signal provenance, market benchmarks and engine metadata; photo anomalies and fraud severity only ever lower the *trust* component, never a verdict
- **Versioned + cached** — `score_version` mixed into a config-signature cache key (`property-intelligence:{room_id}:{sha256(version+weights+thresholds)}`, TTL 900 s via the hardening `safe_cache_*` helpers); invalidation signals on room/image/owner-verification changes, small-sample guards on price (min 3, confidence down <5) and demand (no own signals + area < 3 signals → unavailable)
- **API** — `GET /api/v1/property-intelligence/{id}/` (public) + `/{id}/staff/` (staff) + a read-only `property_intelligence_score` badge on room detail (flag-toggleable); **Agent SDK** — new READ_ONLY `property.intelligence` tool (schema-validated, executor is authoritative, audited `AgentToolCall` + telemetry, enabled-taskable per agent)
- **Admin UI** — read-only **Property Intelligence** inspector per room (`/admin/rooms/room/{id}/property-intelligence/`) rendering score, breakdown, strengths/suggestions, provenance and engine metadata for operators
- **Engineering** — 36 new tests (new `property_intelligence` app, 12 files), 0 migrations, ruff-clean, existing suite green. See [`docs/phase-19-property-intelligence.md`](docs/phase-19-property-intelligence.md)

**Phase 19.0 — Agent SDK / Agentic AI Foundation**

- **Guarded session loop** — `agents.AgentSession` turns a run into a bounded, telemetried conversation: provider resolved through the Phase 18 registry, system prompt rendered through the Phase 18.2 prompt registry (with safe fallback to inline instructions), and a loop bounded by hard guardrails — max turns/6, tool calls/20, tokens/4000, **estimated cost** (exact provider-reported `cost_usd` when present, else Phase 18 cost model), wall-clock timeout, and consecutive tool failures — each landing a machine-readable `termination_reason` for the Phase 18.4 dashboards
- **Server-side tool permission layer** — the authoritative gate (the model only *requests*): read-only tools execute immediately and are audited (`AgentToolCall` with sanitized, depth-bounded results); **state-changing** tools become human-review proposals; **high-risk** tools require role-level **admin** approval (staff is not enough). Proposals are concurrency-safe (`select_for_update`), TTL-expiring (5-min beat), and **idempotent** — applying an applied proposal is a no-op, never re-executes the tool, and rejected/expired proposals can never become actionable
- **Agent registry + seed** — `Agent` definitions (status, audience, permission ceiling, enabled tools, prompt attribution, provider, per-run limits) served at `api/v1/agents/`, seeded by `register_agents` under feature `rentora.agent`
- **Providers** — `ChatLlmProvider` (OpenAI-compatible chat completions, HTTP-error bodies never echoed) and `MockAgentProvider` (deterministic scripted plan for tests; **refused outside test/debug** — no built-in provider means runs terminate with `provider_not_configured`, never invented answers)
- **Safety by construction** — `agents.execute_agent_run` has **no autoretry** (never duplicate side effects) plus its own finished-run idempotency guard; telemetry enrichment failures never break a run; run-outcome notifications + audit on failed/terminated (`ai_alert` stream)
- **API** — minimal public surface (catalog, own conversations/runs/messages) + admin-only registry, run/tool-call, and proposal review/apply endpoints (`/api/v1/agents/`)
- **Engineering** — 38 new tests (1449 BE total, all green), 1 app + 6 models + 1 migration, ruff-clean. See [`docs/phase-19-ai-agents.md`](docs/phase-19-ai-agents.md)

**Phase 18.4 — AI Intelligence Dashboard + Alerts**

- **AI Intelligence Dashboard** — cached admin operations dashboards (TTL 300 s) over telemetry + evaluations + provider health + prompts + Phase 17 drift: per-feature health with drift/quality drills, per-(provider, model) health + **read-only A/B variant comparison** (never switches production), provider availability, cost intelligence, latency, errors, quality/evaluator taxonomy, drift tri-state (`healthy`/`warning`/`critical`/`unknown`), prompt health — 12 endpoints under `api/v1/ai/dashboard/`
- **AI Alerts** — `AIAlertRule` (metric + operator + threshold + scope + severity) and `AIAlert` (full lifecycle), 10 watchable metrics (rates, latencies, cost, evaluation score, drift breach); anti-noise engineered in: **dedup** (repeated breaches fold into one open alert), **cooldown**, **consecutive-checks** streaks; in-app notifications to staff/admins (`ai_alert` type) with deep links; every lifecycle action audited (`ai_intelligence.alert_triggered/acknowledged/resolved/suppressed`)
- **Celery** — `ai_intelligence.evaluate_alert_rules` (beat 5 min) + `ai_intelligence.warm_dashboard_cache` (beat 30 min)
- **Admin UI** — Dashboard → **AI** tab: 11 sub-views (Overview/Features/Models/Providers/Cost/Performance/Errors/Quality/Drift/Prompts/Alerts), hand-rolled SVG trend charts, inline rule editor + acknowledge/resolve/suppress, deep-link alert highlighting
- **Engineering** — 55 new tests (1411 BE total, all green), 2 new models, 3 migrations (`ai_intelligence` 0006+0007, `notifications` 0014), ruff-clean, TS strict + ESLint + production build green. See [`docs/phase-18-4-ai-intelligence-dashboard-alerts.md`](docs/phase-18-4-ai-intelligence-dashboard-alerts.md)

**Phase 18.3 — AI Evaluation Framework**

- **Evaluation Metrics** — `EvaluationMetric` model with metric_key (unique), metric_type (`deterministic`/`heuristic`/`llm_judge`), category, formula, `is_higher_better` direction, default_threshold; `register_metric()` service with idempotent create/update
- **Golden Datasets** — `EvaluationDataset` versioned with `UniqueConstraint(dataset_key, version)`, status lifecycle (`draft` → `published` → `archived`), `EvaluationCase` with input/expected_output/expected_labels/metadata/evaluation_criteria; `create_dataset()`, `create_dataset_version()` (clone), `publish_dataset()`, `archive_dataset()`, `add_cases()` services
- **Evaluator Abstraction** — `evaluators.py` with `register_evaluator()` / `get_evaluator()` / `evaluate_case()` dispatcher; 26 built-in evaluators: search (precision@K, recall@K, NDCG, MRR, relevance_score), classification (accuracy, precision, recall, F1), fraud (precision, recall, F1, FPR, FNR), LLM (task_success, relevance, completeness, hallucination_rate, structured_output_validity), general (exact_match, contains, length_ratio), prediction (MAE, RMSE, R²)
- **Evaluation Runs** — `EvaluationRun` with UUID run_key, status lifecycle (`pending` → `running` → `completed`/`failed`/`cancelled`), `EvaluationCaseResult` with per-metric results, composite score, pass/fail, latency, error tracking; `create_evaluation_run()`, `execute_evaluation_run()`, `cancel_evaluation_run()` services; `execute_evaluation_run_task` Celery task for async execution
- **Thresholds & Regression** — `EvaluationThreshold` (unique per feature+metric), `check_regression()` compares run metrics against thresholds, `get_latest_baselines()` for baseline tracking
- **Model/Prompt Comparison** — `compare_runs()` (side-by-side), `compare_models()` (same feature, different models), `compare_prompts()` (same feature, different prompts), `compare_with_baseline()` with delta analysis
- **Admin API** — 17 new endpoints under `api/v1/ai/eval/`: metrics, datasets, cases, thresholds, runs (CRUD + execute + cancel), case results, comparisons, regression check, baselines
- **Celery** — `execute_evaluation_run_task` (async run execution), `cancel_stale_evaluation_runs` (every 30 min, cancels runs stuck >1 hour)
- **Engineering** — 44 new tests (107 ai_intelligence total), 6 new models, 1 new app file (evaluators.py), migration 0005, ruff-clean. See [`docs/phase-18-3-evaluation-framework.md`](docs/phase-18-3-evaluation-framework.md)

**Phase 18.2 — AI Intelligence Foundation (Prompt Registry + Feature Integration)**

- **Prompt Registry** — `AIPrompt` + `AIPromptVersion` models: versioned prompt/template management with `UniqueConstraint(prompt, version)`, one active version per prompt, `activate`/`deactivate`/`rollback` lifecycle, template safety validation (rejects `API_KEY`/`SECRET`/`PASSWORD`/`TOKEN`/`PRIVATE_KEY`/`AWS_`/`OPENAI_API`/`ANTHROPIC_API` patterns), `render_prompt()` for `{{variable}}` fill, `validate_prompt_variables()` for missing/unused variable detection, immutable templates after creation
- **Feature Flag Integration** — `is_feature_available(feature_id)` now checks both `AIFeatureRegistry.is_enabled` AND linked `FeatureFlag.is_enabled()` (lazy import to avoid circular deps), `AIFeatureRegistry` extended with `status` (active/deprecated/disabled), `owner`, `default_model`, `fallback_strategy`, `feature_flag_key`
- **AI Feature Seeding** — `register_ai_features` management command seeds 30 real AI features from codebase audit (NLP, recommendation, pricing, vision, fraud, KYC, embedding, matching, agreements, analytics)
- **Expanded Admin API** — 18 endpoints under `api/v1/ai/`: 3 feature (list/detail/update), 7 prompt (CRUD + versions), 2 log (list/detail), 3 health (list/stats/update), 3 version management (activate/deactivate/rollback)
- **Engineering** — 63 ai_intelligence tests, 4 database migrations, ruff-clean, existing 1312 tests all pass (was 1270). See [`docs/phase-18-2-prompt-feature-registry.md`](docs/phase-18-2-prompt-feature-registry.md)

**Phase 18.1 — AI Intelligence Foundation (Provider Registry + Telemetry)**

- **AI Intelligence Layer** — new `ai_intelligence` Django app: `AIFeatureRegistry` (central registry of all AI features, providers, costs, settings), `AIExecutionLog` (append-only per-request telemetry with UUID execution_id, latency, tokens, cost, confidence, fallback chain tracking, 4 composite DB indexes), `ProviderHealth` (aggregated provider availability/failure rates over time windows with p95/p99 latency, unique constraint per provider+feature+window)
- **TelemetryMixin** — drop-in mixin for any `BaseProvider` subclass: automatic execution timing (`timed_execution` context manager), non-blocking telemetry logging to `AIExecutionLog`, configurable via `AI_TELEMETRY_ENABLED` setting (default `True`), lazy DB import so providers work without telemetry when flag is off
- **Enhanced ProviderResult** — new fields: `latency_ms`, `input_tokens`, `output_tokens`, `model_name`, `model_version`, `estimated_cost_usd`, `failure_type` (backward-compatible defaults); `ok()` and `fail()` class methods extended with optional telemetry kwargs
- **Cost estimation** — `calculate_estimated_cost(provider, model, tokens)` utility with published pricing for OpenAI (GPT-4 family) and Anthropic (Claude 3 family); returns `Decimal` in USD, 0 for unknown models
- **Provider stats API** — `get_provider_stats(feature_id, provider, hours)` aggregates execution logs into success rate, avg/p95 latency, total cost, total tokens, with per-provider breakdown
- **Admin API** — 7 read-only endpoints under `api/v1/ai/` (feature list/detail, execution log list/detail, provider health list, stats, manual health update), all staff-only
- **Celery beat tasks** — `update_provider_health` (hourly aggregation of execution logs into `ProviderHealth`), `purge_old_execution_logs` (daily cleanup of logs older than `AI_EXECUTION_LOG_RETENTION_DAYS`, default 90)
- **Provider health aggregation** — calculates success rate, p95/p99 latency, timeout counts, token totals, cost totals per (provider, feature) combination; marks providers unhealthy when success_rate drops below 95%
- **Engineering** — 21 new tests, 3 database migrations, ruff-clean, existing 1270 tests all pass. See [`docs/phase-18-ai-intelligence-audit.md`](docs/phase-18-ai-intelligence-audit.md)

**Phase 17 — Graph & Deep Trust (ML Anti-Fraud v2)**

- **Scam-network graph** — `GraphNode`/`GraphEdge` models (PostgreSQL, no external graph DB), `rebuild_graph` full rebuild + `update_graph_incremental` on fraud events, community detection (Union-Find), admin API (`/api/v1/fraud/graph/` — nodes, edges, rebuild, anomalies). Feature-flagged via `GRAPH_ENABLED`
- **KYC liveness + face-match** — `LivenessChallenge`/`LivenessConsent` models, pluggable providers (`rules` deterministic, `http` gateway), OCR confidence thresholds, 5 API endpoints (`/users/liveness/`), `purge_expired_liveness` beat task. Feature-flagged via `KYC_LIVENESS_ENABLED`
- **Photo-geo authenticity** — `RoomImage` GPS fields, `photo_geo` service (haversine mismatch detection), `scan_photo_geo_mismatches` Celery task, `PhotoGeoMismatchesView` admin endpoint. Feature-flagged via `PHOTO_GEO_ENABLED`
- **Fake-review detection** — `review_detector` service (trust scoring: age/length/contact/spam/velocity/similarity, anomaly detection), `scan_review_trust` + `detect_review_anomalies` Celery tasks. Feature-flagged via `REVIEW_TRUST_ENABLED`
- **Model drift monitoring** — `model_monitor` service (check_all_drift, DriftMetric recording, retrain-request creation), `check_model_drift` beat task, admin drift/retrain endpoints. Feature-flagged via `MODEL_DRIFT_ENABLED`
- **Shared provider abstraction** — `BaseProvider`/`ProviderResult`/`ProviderFailure`/`Registry` in `fraud/services/provider_base.py`; all providers (liveness, face-match, OCR) share a common failure taxonomy (`USER_FAILURE`/`PROVIDER_FAILURE`/`SYSTEM_FAILURE`)
- **Security/privacy** — PII masking (phone, NID, email), reason sanitization, audit logging, sensitive-field scrubbing from logs/analytics/URLs/CSVs; `ProviderResult.fail()` auto-sanitizes
- **Engineering** — 262 new backend tests (350 fraud total), 10 stages, pre-commit ruff-clean, Celery beat schedule updated. See [`docs/phase-17-final-report.md`](docs/phase-17-final-report.md) + [`docs/phase-17-graph-trust-audit.md`](docs/phase-17-graph-trust-audit.md)

**Phase 16 — Hardening & Scale**

- **Embeddings & pgvector (vendor-guarded)** — `embeddings/` app: `vector(384)` field on PostgreSQL with a JSON-text fallback so SQLite dev/CI stays green, content-hash dedupe, HNSW index, `index_room`/`remove_room`/`backfill_rooms` tasks + `backfill_embeddings` command; smart-search `_vector_rank` seam and public `GET /api/v1/rooms/{id}/similar/`. Controlled by `VECTOR_SEARCH_ENABLED` (default off)
- **Feature flags + A/B experiments** — `feature_flags/` (cache-backed `is_enabled`, staff CRUD at `/api/v1/flags/`, `sync_flags` seeder) and `experiments/` (deterministic bucketing, persisted assignments, idempotent exposure/conversion wired to the analytics event store, throttled API at `/api/v1/experiments/`)
- **Image pipeline / CDN** — `images/` app generating WebP variants (320/640/960/1280), content-hash filenames for immutable 1-year browser caching, upload hardening (magic-bytes + bomb-guard decode, 128–8000 px bounds, 5 MB cap, max 10 images/listing); KYC/tenant documents moved to **private storage** (out of the public media root); frontend renders `srcset` WebP variants with lazy loading
- **Redis hardening** — `KEY_PREFIX` namespacing, connection-pool/socket timeouts + `protocol=2`, channel-layer prefix; **chat presence re-architected to a self-healing lease model** (per-connection heartbeats, TTL expiry — a crashed worker can no longer leave users stuck "online"); bKash grant-token **single-flight lock**; booking create overlap re-checked under `select_for_update` (closes the double-booking race)
- **Rate limiting / abuse** — proxy-aware client-IP resolution (`NUM_PROXIES`, XFF opt-in), trusted throttle classes wired site-wide, `experiments` scope actually enforced (was a no-op), 429 envelope verified
- **Celery reliability** — broker retry on startup, ack-late + reject-on-worker-lost, soft/hard time limits, default retry policy; prod warns loudly if the broker URL is missing
- **App hardening** — `/health/` liveness endpoint (DB probe, no auth/throttle), `X-Request-ID` correlation middleware, 10 MB request body limits
- **Engineering** — 4 new apps (`embeddings`, `feature_flags`, `experiments`, `images`), ~12 migrations, **960 backend tests passing**, frontend tsc/eslint clean. See [`docs/phase-16-hardening.md`](docs/phase-16-hardening.md)

**Phase 15 — Monetization 2.0 (Revenue)**

- **Landlord SaaS — subscriptions & entitlements** — plan catalog (monthly/yearly), self-serve checkout via SSLCommerz/bKash with **server-side pricing**, subscription activation tied to a confirmed payment (atomic), cancel-at-period-end + renewal, and **entitlements enforced server-side** (`SUBSCRIPTION_FREE_FEATURES`); the AI price-prediction v2 endpoint is gated behind `price_prediction_basic` with a graceful free-tier fallback. See [`docs/phase-15-monetization-2.0.md`](docs/phase-15-monetization-2.0.md)
- **Revenue ledger & commission engine** — idempotent `RevenueLedgerEntry` + `Commission` records (unique `idempotency_key` so a booking/order can never double-credit), platform/partner splits per scope with default rates (broker 2.0%, corporate 1.0%, marketplace 10%, insurance 8%, credit 3%), a **payout lifecycle** (pending → approved → paid / rejected) that deducts the balance atomically and masks account details, and a Celery-beat **subscription renewal + reminder** pipeline
- **Verified Broker/Agent Network** — broker profiles with license + referral code, rule-based auto-screen verification, **attributed booking commissions** (signal-driven, idempotent), broker dashboard (balance, pending/paid, recent commissions) and self-serve payout requests
- **B2B Corporate Housing** — corporate accounts (pending/active/suspended), member invites, **bulk booking with partial success**, corporate invoices (draft → generate), company-admin overview/approvals and platform-admin controls
- **Add-on Services Marketplace** — provider registration, category-filtered service catalog, order lifecycle (pending → confirmed → completed/canceled), **per-booking AI cross-sell recommendations** and provider commission
- **Insurance & Credit Partnerships** — provider-agnostic partner abstraction with a rule-based insurance provider: instant quotes, issue/decline/cancel policies, product catalog, and renter credit eligibility (pre-approved limit); every action auditable
- **Admin revenue centre** — revenue dashboard (gross/platform revenue, MRR, pending partner obligations), live ledger, and a payout queue (`/dashboard?tab=revenue`)
- **Engineering** — 6 new backend apps (`subscriptions`, `monetization`, `brokers`, `corporate`, `marketplace`, `partner_services`), 11 migrations, `manage.py seed_monetization`, renewal/reminder beat tasks, **884 backend + 373 frontend tests**, tsc/eslint/prettier clean. Frontend: `/services` page + Dashboard tabs `monetization` / `broker` / `corporate` / `revenue`, EN/BN i18n

**Phase 15 — Communication & Trust AI**

- **Chat translation (B1)** — auto-detects source language, translates chat messages EN↔BN with Google Translate fallback; quality flag (`full`/`phrase`/`none`) shown honestly in the UI
- **Support copilot (B2)** — grounded FAQ matcher against help library; returns answer + Bangla translation + matched keywords; honest fallback when no article matches
- **Voice TTS (B3)** — Web Speech API integration on copilot assistant replies; respect `speechSynthesis` availability with feature-detection guard
- **KYC OCR (C4)** — auto-extracts NID number, name, DOB from uploaded verification documents with confidence score; displayed in TenantKycCard with honesty note
- **Review summary (C5)** — AI-generated summary of room reviews with sentiment breakdown (positive/neutral/negative %) and topic tags; shown in ReviewsSection
- **Market report (C6)** — weekly area-level rental analytics (median price, WoW movement, index); AdminAnalyticsPanel visualization; email distribution to opted-in landlords
- **Dynamic pricing v2 (C7)** — demand-momentum-adjusted price windows with area-specific factor drivers; replaces static v1 with time-series-informed recommendations
- **Fraud rings (D8)** — detects coordinated accounts via shared phone (strong link) and shared audit IP + same area (weak link); flagged rings surfaced in AdminFraudPanel
- **Bug fix** — fixed SQLite `DISTINCT` + `ORDER BY` gotcha in `market_report.py` and `forecast.py`; added `.order_by("area")` to deduplicate area rows

**Phase 14 — AI v3: Vision & Content AI**

- **Photo intelligence** — `rooms/vision.py` fingerprints a listing's photos (pHash + 64-bucket colour histogram + brightness + palette, Pillow-only, offline) and derives honest, confidence-scored observations: lighting, tone, décor, composition. `POST /api/v1/rooms/<id>/vision/analyze/` stores a `RoomVisionAnalysis` (OneToOne), `GET /vision/` serves it, `POST /vision/description/` drafts a copy-ready title + description from the **actual photos** (reuses the AI draft pipeline with the vision image profile), and suggested amenity tags can be **reviewed then applied** to the listing. Object-level tags need an optional `http` vision gateway (`VISION_PROVIDER=http`) with graceful fallback; every response carries the honesty note that this is statistical pixel vision, not object recognition. See [`docs/phase-14-ai-v3.md`](docs/phase-14-ai-v3.md)
- **AI image search** — `POST /api/v1/rooms/vision/search/` (public, throttled 30/min): upload any room photo, get look-alike listings ranked **50% phash + 25% histogram + 25% brightness** with match scores and reasons; the rooms grid shows `88% match` badges.
- **Frontend** — `VisionCard` panel in the landlord dashboard (My Listings) with palette swatches, evidence chips, Apply tags, AI draft + copy; Image search dialog on `/rooms` with photo preview and results mode; all strings in English + বাংলা.
- **Engineering** — 716 backend (was 689) + 342 frontend (was 333) tests, tsc/eslint/prettier clean, migration `rooms/0007_roomvisionanalysis.py`, 3 new Playwright screenshots (`capture_phase14_shots.mjs`).

**Phase 13 — Reach (SMS OTP, WhatsApp sharing, area SEO)**

- **SMS OTP sign-in** — phone-first login for the Bangladesh market: `POST /api/v1/auth/sms/request|verify/` with a SHA-256-hashed challenge (TTL 600s, max 5 attempts, 30s resend cooldown), masked-phone responses (`+8801••••78`) and **auto-registration** for new numbers. Provider contract (`users.sms.send_sms`) ships `console` (logs the code — zero-config dev/CI) and `http` (generic gateway POST); **disabled by default** (`SMS_OTP_ENABLED=False` → endpoints answer `503` until a real gateway is plugged in). 19 tests including the disabled→503 path. See [`docs/phase-13-reach.md`](docs/phase-13-reach.md)
- **WhatsApp listing share with AI summary** — **Share on WhatsApp** on every room card + in the room modal. `GET /api/v1/copilot/share-summary/<id>/` builds a compact, deterministic summary **only from public listing fields** (no owner contact details); the frontend falls back to a client-side summary when the AI call fails, then opens `wa.me/?text=…` pre-filled with the summary + deep link.
- **Per-area SEO landing pages** — `/rooms/:areaSlug` for 10 Dhaka areas (own `<title>` "Rooms for rent in Dhanmondi, Dhaka", meta description, live room grid, `?room=<id>` deep links), a navbar **Areas** dropdown, `npm run generate:sitemap` → `public/sitemap.xml` (5 core + 10 area routes), and `robots.txt` updated. Honest limits: SPA, not SSR — the area pages are crawlable metadata + sitemap.
- **Lighthouse gate in CI** — `scripts/lighthouse-gate.mjs` audits the **built** app (chrome-launcher, `--min-score` threshold 70; local run **70/70 PASS**) and a new `lighthouse` CI job uploads the report as an artifact.
- **Engineering** — 689 backend (was 667) + 333 frontend (was 322) tests, tsc/eslint/prettier clean, migration `users/0010_smsotpchallenge.py`. React Native remains a separate, unfunded track ([`docs/MOBILE_APP_PLAN.md`](docs/MOBILE_APP_PLAN.md)).

**Phase 12 — Trust & Safety V2 (Marketplace Integrity)**

- **Tenant KYC + verified-tenant badge** — tenants upload a NID/passport (multipart, MIME/size-validated, UUID-renamed private storage); statuses not_started → pending → verified / rejected / needs_review / expired. Landlords only ever see the **✓ Identity Verified badge** — never the document, the NID number, or the file URL. Admin queue (`/admin/trust/tenant-verification`) with approve/reject/resubmission, each decision audited (`tenant_kyc.*`) and notified. Badge renders in chat, booking requests and the tenant profile. See [`docs/TENANT_KYC.md`](docs/TENANT_KYC.md)
- **Chat safety engine** — the fraud engine now analyses every chat message: suspicious payment requests, payment/bKash redirects, phishing URLs, contact-info harvesting, impersonation, scam phrases and urgency. Outcomes: LOW (allow) / MEDIUM (warn banner) / HIGH (flag + warning) / CRITICAL (blocked message, replaced with a safety notice — never silently deleted). Admin feed `GET /chat/safety/events/` (metadata only, no raw content). See [`docs/CHAT_SAFETY.md`](docs/CHAT_SAFETY.md)
- **Report / block / dispute** — report a user, message (anchored to the exact message) or listing across 7 categories (scam, harassment, fake listing, payment fraud, impersonation, spam, other); block/unblock a user closes the conversation both ways (server-enforced); structured moderation tickets with admin warn / restrict / suspend / escalate actions — all audited (`report.*`, `user.blocked`) and both parties notified
- **Photo + review moderation** — the moderation app auto-scores every new review (URLs, phone/email, spam phrasing, all-caps/exclamation, gibberish, cross-user duplicate text, review velocity) and photo (pHash duplicate-image reuse, blank-image guard) — high-risk content is **held** in a moderation queue instead of published; admin approve/reject with notes, audited (`content_moderated`) and the author notified
- **Dispute resolution + deposit protection** — one structured dispute per approved booking (6 categories: deposit, property condition, cancellation, misrepresentation, payment, other) with participant-only evidence (text/photo/document, IDOR-guarded), a full status lifecycle, and admin resolution (release-to-landlord / refund-to-tenant / partial) that marks the booking deposit released/refunded. Wording is honest — the platform never claims "escrow". See [`docs/phase-12-trust-safety-v2.md`](docs/phase-12-trust-safety-v2.md)
- **Admin Trust & Safety Operations Center** — one dashboard (`/dashboard?tab=trust`) aggregating KYC pending, chat-safety events, open reports, moderation queues and open disputes with sub-tabs into each queue, plus the generic read-only **audit trail** (`GET /api/v1/audit/`) covering every Phase 12 decision
- **Engineering** — 3 new backend apps (moderation, disputes + audit endpoint) and 6 new frontend admin/user panels; **473 backend + 312 frontend tests**, tsc/eslint/prettier clean

**Phase 12 P0 — Progressive Web App (installable app)**

- **Installable PWA** — `manifest.webmanifest` with `standalone` display, `#ea580c` theme (design-token brand), 192/512 standard + **maskable** icons, Apple-touch + favicon set (32→144), generated reproducibly from the brand (`scripts/generate_pwa_icons.py`) and validated in CI against the **built** app (`scripts/validate-pwa.mjs`)
- **Native install experience** — the browser's `beforeinstallprompt` is captured but suppressed until a subtle navbar **"Install app"** CTA is clicked, so Rentora never fires a surprise popup; the CTA disappears after install, and a dismissal cools off for a week (`usePwaInstall`)
- **Standalone + deep links** — works installed on desktop & mobile; routing, auth, the map (viewport/radius/destination URL sync), voice search, Copilot and both dashboards behave identically in standalone mode
- **Safe service-worker caching** — the push worker now also caches a versioned `rentora-static-v1` app shell + static assets only; **`/api/*` (auth, private, admin, fraud, payment) is never cached**, navigations are network-first with an offline shell fallback, and only our own `rentora-static-*` caches are ever cleaned
- **Update UX** — when a new build takes over, a "A new version of Rentora is available **[Refresh] [Later]**" banner appears (Later remembered for 24h); the initial install never shows it (`usePwaUpdate`)
- **Graceful offline** — an amber "You're offline" banner (safe-area aware) while already-loaded UI stays visible — never fake listings or stale data
- **Shortcuts** — Search Rooms `/rooms` · Explore Map `/map` · Post Listing `/dashboard?tab=listings`
- **Branding** — the app name is now **Rentora 🇧🇩** (gradient wordmark in the navbar/footer, Bangladesh-flag badge) matching the push notifications, Copilot and README
- **Engineering** — 11 new unit tests (`src/lib/pwa.test.ts`), PWA validation wired into the Frontend CI job. See [`docs/PWA.md`](docs/PWA.md)

**Phase 12 P1 — Offline & App Polish**

- **Offline search** — the Rooms page now serves from an **IndexedDB cache of PUBLIC listings** (24 h TTL, room details 7 d) with client-side re-filtering when the network drops, plus a "📡 showing N cached of M (offline)" pill; **auth/private/admin/fraud/payment data is never cached** (`rentora-offline` DB holds only public room lists/details + the action queue)
- **Background sync** — offline actions (wishlist toggles, saved-search checks) are queued and replayed on reconnect via `registration.sync` + `online`/`visibilitychange` fallbacks; failed replays are re-queued, never dropped
- **Periodic Background Sync** (research-informed, feasible subset) — when installed, Chromium-only daily `rentora-refresh` keeps the PUBLIC cache fresh; Notification Triggers API documented as future scope (not shipped in any browser)
- **Splash screens** — 11 device-matched **Apple splash screens** + **dark maskable icon** (`maskable-dark-512`), all generated from the brand by `scripts/generate_pwa_icons.py`
- **iOS install hint** — one-time, dismissible "Add to Home Screen" card (Safari has no install-prompt API)
- **Flag everywhere** — brand name now uses an **inline SVG Bangladesh flag** (`BangladeshFlag` component) that renders identically on every OS — no more "BD" letters where the emoji is missing
- **Lighthouse (prod build)** — Performance **84** · Accessibility **93** · Best practices **96** · SEO **82** (`robots.txt` added); Lighthouse 12+ dropped the PWA category — installability enforced by CI `validate-pwa.mjs` instead
- **Engineering** — 17 new unit tests (230 frontend total), tsc/eslint/prettier clean

**Map Intelligence v3 (Phase 7 v3) — Interactions + Dark Mode + Dhaka Hierarchy**

- **Dark map fixed** — lifted CARTO dark raster paint (brightness floor 0.2, contrast 0.2) keeps roads + street labels readable instead of near-black; dark-fallback also lifted; overlays now visible in dark mode
- **Dark layer contrast QA** — every overlay gets dark-mode paints via a theme-swap effect (`setPaintProperty`, map state preserved): 🎓/🚇 dots brighten, MRT corridor core brightens with subtle casing, heatmap switches to green-400/amber-400/red-400 at higher opacity with dark strokes, cluster rings darken, isochrone bands get stronger fills (0.1 → 0.22) + white outlines, radius/metro-reach rings brighten; dark popup card (no more white flash); paint values in `lib/mapInteractions` `THEME_PAINTS` (unit-tested)
- **Every map element is interactive now** — click a 🎓 university or 🚇 metro station → real nearby stats (count · avg/range rent within ~2 km) + "Find rooms near…" CTA; MRT Line-6 corridor clickable; price-heatmap click → clicked area's real stats; 10/20/30-min walking bands clickable → rooms inside
- **Map ↔ list sync** — list click flies + highlights the pin; map pin click scrolls the list item into view
- **Room deep links** — `?room=123` in a shared map URL reopens the listing on load
- **Structured Dhaka hierarchy** — new `GET /api/v1/rooms/area-hierarchy/` (20 main areas → 30+ sub-areas/neighbourhoods, parent links, Bangla + English aliases); sub-area search ("Mirpur 10", "Uttara Sector 7", "ধানমন্ডি ২৭") resolves with its parent district shown
- **Area boundary polygons** — `GET /api/v1/rooms/area-boundaries/`: approximate boundary bubbles (honest circles, `approx_radius_km`, not fake borders) — main areas strong orange rings (z≈9.5+), sub-areas blue (z≈11.5+), neighbourhoods violet (z≈13.5+), click → real area stats; dark-mode paints included
- **Expanded landmark layer** — 🏥 hospitals, 🛒 markets, 🌳 parks, 🕌 mosques, 🚌 bus terminals join universities & metro (63 real Dhaka places: Square Hospital, New Market, Baitul Mukarram, Gabtoli/Saidabad terminals…). Everyday categories share one **clustered source**: count bubble at low zoom (click → zoom in) → per-kind dots as you zoom, each with its own minzoom; every dot opens real nearby-room stats + "Rooms near here →" radius CTA; dark mode brightens each category
- **Nearby-landmark chips** — every listing popup shows the nearest useful places around it (🚇 7 min Metro · 🎓 12 min University — real landmarks only, nearest of each category within ~3 km, honest walk estimates); clicking a chip flies to the place + starts a radius search
- **Zoom-aware area labels** — area bubbles carry their real centre (`lat`/`lng`), rendered as labels with zoom-based hierarchy (main z≈10, sub z≈12.5, neighbourhood z≈14.5) so the map never drowns in text; theme-aware text + halo
- **Boundary click → area filter** — clicking an area bubble highlights it (selected > hover > base feature-state), shows its real stats and **filters the room list + URL** (`?area=…`); empty click clears it
- **Landmark-nearby list search** — filter the room list by "near a metro / university / hospital…" within 0.5–2 km (`?near=<kind>&distance=<km>`), resolved to the nearest real landmark, map flies there once

**Phase 9 — Operate It (Reliability & Observability)**

- **Sentry error tracking** — backend (Django/Celery integrations) and frontend (`@sentry/react`); initialised from `SENTRY_DSN` / `VITE_SENTRY_DSN` and a **no-op when unset**, so local dev and CI never send events. Frontend error boundary forwards component stacks.
- **Structured JSON logging** — a stdlib-only `JSONFormatter` (`config/logging.py`) emits one JSON object per line when `JSON_LOGS=True`; stable keys (timestamp/level/logger/message) plus caller extras, ready for any log shipper.
- **Celery + Celery Beat** — `config/celery.py` with a **zero-config local mode**: an empty `CELERY_BROKER_URL` runs tasks eagerly (synchronously, no Redis), production sets a Redis broker and tasks go async. Scheduled maintenance moved onto the beat schedule: hourly tier expiry, daily market-stat refresh, daily catalogue fraud re-scan, daily rent reminders (`rooms/pricing/fraud/payments/tasks.py`).
- **Fraud hardening** — the auto-scan now runs through a Celery task wrapped in try/except so a detector or queue failure can **never break room creation**; individual detector failures are isolated (logged + skipped, the rest still run); the flag path now also emails the landlord.
- **Branded HTML transactional emails** — `notifications/emails.py` + `notifications/templates/emails/` (base shell + OTP code, recovery codes, booking status, fraud flag, promotion expiry), each with a plain-text fallback. Wired into OTP delivery, 2FA-enable recovery codes, booking lifecycle signals, fraud flags, and `expire_listings`.
- **Audit log** — new `audit` app: an append-only `AuditLogEntry` table records who did what to which object (with IP) for sensitive actions. Wired into fraud-report review and 2FA enable/disable; the Django admin view is read-only so the trail cannot be rewritten.
- **Backup & restore runbook** — `scripts/backup_db.py` (cross-platform; SQLite consistent copy via the backup API, PostgreSQL via `pg_dump`, pruning with `--keep`) plus `docs/ops/backup-restore.md` covering restore, media, and a quarterly restore drill.
- **KYC SLA breach alerts** — a daily Celery beat task (`alert_kyc_sla_breaches`) watches the KYC review queue and alerts every admin (in-app notification + branded email) when a **breach** fires: an application stuck past 48h, or decisions this week trailing last week. Deduplicated atomically per day per condition (`get_or_create` on a date-stamped title), so a retried cron never stacks identical alerts.

**Phase 10 — Grow It (Growth & Personalization)**

- **AI recommendations v2 — Similar Rooms** — every room modal now shows a **content-based similar-rooms carousel** (`GET /recommendations/similar/<id>/`): listings ranked by area, room type, price band and amenity overlap, with a match % and explainable reasons ("Same area: Dhanmondi · Similar amenities"). Same feature vector family as the personalized recommendations, so the two surfaces agree.
- **Search v2 — full-text + typo tolerance** — room search (`?q=`) is now real full-text on **PostgreSQL** (`SearchVector`/`SearchRank` with stemming + `pg_trgm` fuzzy similarity so typos still match) with an automatic **`icontains` fallback on SQLite**, so dev/CI/prod behave identically. `?q=` still composes with area/price/gender filters and geo queries.
- **Saved searches + alerts** — the Rooms page gets a **Saved searches** bar: save the current filters (with a name), and a daily Celery beat task (`check_saved_searches`) notifies you in-app whenever a **new** matching listing appears (never re-alerts the same rooms — `last_checked_at` advances every run). Manual "check now" from the list too.
- **Browser push notifications** — subscribe once from the Dashboard (**Browser notifications** card) and every in-app notification (bookings, chat, fraud flags, KYC decisions, saved-search matches) is also **pushed to your browser even when Rentora is closed**. VAPID keys generated by `scripts/generate_vapid.py` (`pywebpush` server-side + `public/sw.js` service worker); dead subscriptions are auto-pruned (410 Gone), and no VAPID = safe no-op for local dev/CI.
- **Referral program** — every account gets a unique referral code; share your **invite link** (Dashboard → **Invite friends** card, with WhatsApp/Facebook shortcuts) and signups landing with `?ref=CODE` are attributed to you (`GET /users/referral/` shows your code, link and who joined). `ref` is optional at register — the code is just a query param on the shared URL.
- **Wishlist sharing** — one tap **Share wishlist** copies a public, unguessable link (`/wishlist/share/<token>/`) — room summaries only, no personal info, 404 on bad tokens so they can't be enumerated.
- **Landlord tools — listing insights** — new Dashboard **Insights** tab: per-listing engagement (**views 7d/30d** tracked from room-detail visits, deduplicated), wishlist saves, booking requests vs approvals, and **price vs area-average** positioning (from the market-stats table) with a red/green delta badge — plus bulk listing creation (`POST /rooms/bulk/`).
- **Reviews v2 — replies, photos, rating breakdown** — reviews now support **landlord replies** (inline form for the room owner, shown under the review), **tenant photo reviews**, and the room modal shows a **rating breakdown** (5★ histogram + average + verified-stay badges) from `GET /reviews/summary/?room=`.
- **Engineering** — 388 automated tests (210 backend + 178 frontend), ruff/eslint/prettier clean, migrations include a backfill so every existing account gets a unique referral code + wishlist token.

---

## 🆕 Changelog — What's New in v2.0

**Tier-1 Quick Wins (polish batch)**

- **Chat: message search + edit/delete (audited)** — search any message in a
  conversation, edit your own text messages (re-runs the chat-safety engine),
  and soft-delete messages. Every edit/delete writes an audit entry
  (`chat.message.edited` / `chat.message.deleted`) and updates all open
  clients in real time over the WebSocket.
- **Saved-search daily email digest** — one branded email per day with new
  listings matching your saved searches (deduped across searches, own
  listings never emailed, per-account opt-out `digest_emails_enabled`),
  delivered through the rate-limited alert email guard.
- **Report/block abuse guard** — the report endpoint is now rate-limited
  (10/hour) and a duplicate report of the same target while a report is
  still open returns the existing ticket instead of stacking the queue.
- **Semantic search cache** — identical smart-search / Copilot queries over
  the same room pool reuse the cached ranking instead of recomputing
  embeddings (personalized + debug requests bypass the cache).
- **Security headers + security.txt** — CSP, `Referrer-Policy`, `nosniff`,
  `Permissions-Policy` and HSTS (prod) on every response; RFC 9116
  `/.well-known/security.txt`.
- **Dependency bump audit** — safe patch/minor bumps applied to backend +
  frontend deps and documented in `docs/tier1-dependency-audit.md` (majors
  like React 19 / Vite 8 / Django 6 held for a dedicated upgrade cycle).

**Tier-3 Upgrades (RAG Copilot, i18n, embeddings, E2E, trust signals)**

- **RAG-powered Copilot (listing mode)** — the Copilot is no longer
  search-only: from any room modal, **Ask Copilot about this listing** opens
  a conversation *grounded on that single listing* (`listing_id` on
  `POST /api/v1/copilot/chat/`, fact card at `GET
  /api/v1/copilot/listing/<id>/`). Questions about price / amenities / area /
  type / size / gender / verification / availability are answered strictly
  from the listing's public fields (bilingual keyword detection, EN + BN +
  Banglish); anything the listing doesn't state is refused explicitly — no
  hallucination by construction. Deterministic map intel (nearest metro)
  included in the fact card.
- **Full EN ⇄ বাংলা UI toggle** — `react-i18next` + `i18next` with inline
  dictionaries (`src/i18n/en.json` / `bn.json`), a **বাংলা/EN toggle in the
  navbar**, language persisted in `localStorage` and applied before first
  render (no flash of the wrong language), `document.documentElement.lang`
  set for accessibility, and English fallback for any untranslated key. Core
  surfaces translated: navbar, footer, home hero, room cards, room modal,
  copilot widget, trust badges, search labels.
- **Production-grade neural embeddings** — `SEMANTIC_EMBEDDING_MODE`
  (`auto`/`neural`/`lite`) selects the provider, the embedding matrix is
  **persisted to disk** keyed by provider + data fingerprint
  (`SEMANTIC_EMBEDDING_CACHE_DIR`, default `media/embeddings`) so every
  worker reuses the prebuilt neural matrix instead of re-encoding the corpus
  and re-downloading the model, and `python manage.py prebuild_embeddings`
  warms the cache after deploy. `neural` mode degrades to lite with a
  warning when sentence-transformers is missing — search never breaks.
- **E2E suite expansion (trust-flow + map)** — new tagged E2E tests driving
  the real API: the full trust chain (report → duplicate-report guard →
  admin queue → dismiss → block → chat refused → unblock → audit trail,
  with `report.created` / `user.blocked` / `user.unblocked` audit events
  added where the spec required them) and the map flow (map search → area
  stats → commute ETA with OSRM-off graceful fallback).
- **Tenant behavioral trust signals** — transparent, data-backed signals
  beside the identity badge: **completed bookings** (approved bookings whose
  deposit was refunded or stay ended — never pending/in-progress),
  exposed as `trust_signals` on the user details, chat participants and
  booking payloads, and rendered as a ✓ N completed bookings chip in chat
  headers, the verified-tenant badge and the landlord dashboard.
- **Engineering** — 610 backend + 320 frontend tests, ruff/eslint/tsc clean.

**Tier-4 Upgrades (AI tools, comparison, forecast, Playwright E2E, hosted KYC)**

- **🤝 AI Rental Advisor** (`POST /api/v1/copilot/advisor/`) — budget + income
  in → a grounded, transparent budget plan (rent cap, suggested areas, monthly
  breakdown) built from live listing data, never invented figures.
- **💬 AI Negotiation Assistant** (`POST /api/v1/copilot/negotiate/`) — picks
  the right counter-offer bracket from comparable listings in the same area
  and drafts a polite EN/BN message the tenant can send directly from the
  listing modal (**Draft negotiation**).
- **📄 AI Rental Agreement Checker** (`POST /api/v1/copilot/agreement-check/`) —
  paste a rental agreement; deterministic rules flag one-sided clauses,
  advance-payment risk and missing Bangladesh-standard fields (refund terms,
  notice period, deposit return), with plain-language advice.
- **🏠 Landlord Copilot** (`POST /api/v1/copilot/landlord/`) — landlord-facing
  insights for any owned listing: price position vs the market median,
  listing-quality score, occupancy risk and pricing suggestions.
- **📊 AI Property Comparison** (`GET /api/v1/rooms/compare/?ids=1,2`) — select
  2–5 rooms and compare price, size, amenities, ratings and per-area value in
  a dedicated drawer with clear winner call-outs.
- **📈 Demand Forecasting** (`GET /api/v1/analytics/forecast/`) — lightweight
  time-series forecast of rental demand for an area + room type, powering
  smart alerts and landlord insight.
- **🔔 Smart AI Alerts** (`GET /api/v1/notifications/smart/`) — your
  notification inbox re-ranked by a transparent priority score (0–100) with a
  plain-language `reason` for every item.
- **🧠 Hosted neural embeddings** — `SEMANTIC_EMBEDDING_PROVIDER=hosted` uses a
  remote Hugging Face endpoint (falling back to local lite mode gracefully);
  the disk-persisted matrix stays the single source of truth.
- **🪪 Automated KYC pre-verification** — a pluggable provider
  (`USERS_KYC_PROVIDER`, mock/auto modes) pre-screens NID submissions with
  deterministic checks (document number shape, date sanity, duplicate guard),
  auto-approves only clear passes and routes everything else to the existing
  manual admin review — the human fallback is always in place.
- **🧪 Browser-level Playwright E2E** — a real-browser layer (`frontend/e2e`,
  `npm run test:e2e`) that boots the dev server and verifies the app renders,
  searches, opens the Copilot and answers a listing question; wired into CI
  as a separate job.
- **Engineering** — 667 backend + 322 frontend tests (989 total), ruff/eslint/tsc clean, OpenAPI↔TS schema contract enforced.

**Tier-5 Upgrades (funnel analytics, photo forensics v2, price advisor, Copilot vision, AI drafts)**

- **📈 Conversion funnel fully wired** — the last missing analytics steps are
  now emitted server-side: `booking_confirmed` (on approval, via the booking
  signal) and `payment_completed` (on the payment SUCCESS transition) join the
  client-fired `page_view` → `room_view` → `chat_started` → `booking_requested`
  steps, so the self-hosted analytics funnel reflects real conversion (667
  backend tests verify attribution + no-PII).
- **🖼️ Photo forensics v2** — the existing ELA/watermark-band pipeline gains
  two deterministic heuristics: **text-overlay detection** (dark strokes on a
  bright photo — captions/phone-number watermarks) and **repeated-pattern
  detection** (tiled/diagonal watermarks that real photos never contain), both
  tuned against synthetic attacks and the existing clean-photo suite.
- **💹 Per-listing price recommendation** (`GET /api/v1/rooms/<id>/price-recommendation/`,
  owner/admin) — the demand-forecasting engine is now linked to *individual*
  listings: area demand index + market position + the listing's own
  30-day interest signals produce a grounded raise/hold/lower verdict with a
  suggested price and plain-language reasons (a review aid, never an
  automatic change).
- **👁️ Copilot image understanding** — ask "দেখতে কেমন? / what does it look
  like?" and the listing-mode Copilot answers from the *actual* photos using
  deterministic pixel statistics (brightness, colourfulness, dominant tones),
  explicitly labelling the answer as statistical — no invented captions.
- **✍️ AI listing draft** (`POST /api/v1/rooms/generate-description/`) —
  landlords get a one-click **✨ AI draft** in the listing form: a title +
  description + amenity tags built deterministically from the fields they've
  already filled, always editable before publishing.
- **Engineering** — 667 backend + 322 frontend tests (989 total), ruff/eslint/tsc clean, OpenAPI↔TS schema contract enforced.

**Tier-2 Medium Upgrades (trust, analytics & infra)**

- **AI chat-safety classifier** — a learned Naive-Bayes layer (trained on
  real EN+BN rental conversations, Unicode-aware tokenization) sits on top
  of the deterministic rules: it flags scam-like messages the rules miss,
  can only ever *flag for human review* (never block), and every model
  mistake degrades to a queue item. Toggle: `CHAT_SAFETY_ML_ENABLED`.
- **Self-hosted analytics** — first-party event capture (`POST
  /api/v1/analytics/events/`, auth-optional, bounded payloads, throttled,
  no PII) + admin dashboard (`GET /api/v1/analytics/summary/`): event
  totals, top events/pages, daily volume and the **conversion funnel**
  (page_view → room_view → chat_started → booking_requested →
  booking_confirmed → payment_completed, distinct users per step). New
  **Analytics** tab in the Trust & Safety Operations Center.
- **Photo manipulation / watermark detection** — pure-Pillow forensics on
  listing images: block-level **ELA consistency** (catches the classic
  multi-generation paste attack without flagging honest recompression),
  watermark-band / editor-EXIF / tiny-low-quality heuristics. Wired into
  the fraud scan as the `manipulated_image` detector.
- **OSRM commute ETA** — real road-network ETA for the map: car/CNG/bus
  via a self-hostable OSRM server (`GET /api/v1/rooms/eta/`), cached 15
  min, and a **graceful fallback** to the straight-line/MRT heuristics
  when routing is down (`OSRM_ENABLED`).
- **ClamAV virus scan for chat uploads** — optional malware scan on
  attachments; a positive detection rejects the file, an unreachable
  scanner degrades to clean-by-default (type/size checks stay the gate).
  Opt-in: `CLAMAV_ENABLED`.
- **KYC automated pre-screening** — every tenant verification submission
  is scored automatically (document parses, cross-account reuse via pHash,
  readable size, profile completeness, attempt history from the audit
  log) and the admin queue gets an **approve/review recommendation + the
  reasons** — the human decision stays the source of truth.
- **react-router v7** — upgraded from v6 (fixes the last 2 moderate npm
  audit findings; `npm audit` is now clean).

**Paid Listing Tiers (first revenue stream)**

- Free → **Featured** (৳199/30d) → **Premium** (৳499/30d) promotion payments via SSLCommerz/bKash
- Server-side pricing, ownership + duplicate-tier guards, double-click race protection, premium-first search ordering
- Expired promotions auto-revert to Free (`expire_listings` command + query-time `effective_tier`)
- Dashboard **Listings** tab with Promote modal; gold/orange tier badges on cards

**Roommate Matching** — weighted scoring (budget/area/room-type/gender/lifestyle) with request/approve flow

**Fraud Detection** — 6-detector engine (duplicate title, copied description, price anomaly vs market percentiles, missing images, unverified owner, rapid spam) with auto-scan + admin review queue**Auth & Trust**

- Fresh **login/register redesign** (animated Dribbble-style auth page)
- **Deep password strength meter** — zxcvbn-ts engine: real entropy (`~10^N` guesses), common-password detection ("top-10 common password" warnings), 4-segment meter, live confirm-match indicator
- **HaveIBeenPwned breach check** — k-anonymity lookup (only the first 5 chars of the SHA-1 hash leave the device); shows ⚠️ breached / ✓ safe / unknown status on the register form**Two-Factor Authentication (email OTP)**
- Password + one-time code — enabled per account from the Dashboard; **enabling is email-verified**: password first, then a code emailed to the address must be confirmed, so an account can never be locked behind an unreachable inbox
- **10 one-time recovery codes** minted at enable (shown exactly once, stored hashed) — sign in with one if you lose email access; deleted when 2FA is disabled
- OTP codes stored **hashed** (SHA-256) in the DB; 10-minute TTL, 5-attempt lockout, 30s resend cooldown, stale challenges auto-invalidated on re-login
- Login returns a pending challenge (masked destination, e.g. `r***@rentora.com`); tokens are only issued after the code verifies — no tokens leak at the password step

**Passkeys (WebAuthn / FIDO2)**

- Passwordless sign-in with a fingerprint, face, or device PIN — `py_webauthn` server-side, `@simplewebauthn/browser` client-side
- **Conditional UI** on the login form: passkeys surface in the browser's native autofill; a manual "Sign in with a passkey" button is the fallback
- Only **public keys** stored; sign counters tracked for clone/replay protection; 2FA-enabled accounts still get the email-OTP step after the passkey
- Register/revoke from the Dashboard → Security → Passkeys
- Sign in with **username or email**; **duplicate-email registration now blocked** (serializer + DB unique constraint) with a readable error message
- Already-logged-in users are redirected from `/auth` to their dashboard

**Interactive Map (Phase 7)**

- **MapLibre GL JS** map of Dhaka — OpenStreetMap tiles, key-free, with dark/light tile switching that follows the app theme
- **Price marker pins** — every listing is a tappable pin showing its price (`৳12k`), coloured by tier (free orange / featured blue / premium amber) so promoted rooms pop exactly like the list
- **Marker clustering** — with many listings in view, pins collapse into numbered cluster circles that show the **room count + average rent** (click one for a count/price-range popup, then it zooms in); toggle between **Clustered** and **Pins** modes
- **Viewport sync** — panning/zooming refetches rooms inside the visible `bbox` (debounced 300ms), so the map and the room count always match what's on screen
- **Radius search** — click a point on the map (or a university chip) and drag a slider to see rooms within 0.5–5 km, powered by the geo backend's `near_lat`/`near_lng` + `radius_km`
- **Travel-time overlay** — with a search point active, toggle **Travel** to draw walking isochrones (10/20/30 min bands, green → amber → red) so tenants see how far they can get on foot from a university, metro or office
- **Street search + autocomplete** — type a street, area or station ("gulshan", "mirpur road", "shahbagh") and pick a suggestion to fly there and start a radius search, powered by the curated Dhaka gazetteer **with an OpenStreetMap Nominatim fallback** (`/rooms/geocode/`) so even streets outside the curated list geocode
- **Get Directions + travel-mode toggle** — every room popup shows walking **and** driving ETA ("≈ 8 min walk · ≈ 2 min drive") plus a 🚶 **Walk** / 🚗 **Drive** / 🚇 **Transit** picker that opens Google Maps with the right route pre-filled (origin = your search point)
- **Metro ETA in popups** — each popup lists the nearest MRT station with distance + walking time ("🚇 Kawran Bazar MRT · 2.0 km · ≈ 27 min walk") from the backend's `proximity` annotation
- **Area count chips** — the current viewport's areas appear as tappable chips with live room counts ("Dhanmondi 3 · Mirpur 3") from `/rooms/summary/` `by_area`; tap one to fly there and start a radius search
- **Metro route corridor** — MRT Line 6 is drawn as a polyline through its stations (Uttara → Motijheel), visible with the Metro toggle or whenever the travel overlay is active; stations within a 30-minute walk of the search point get a highlighted ring
- **Room-count API badge** — the "N of M rooms in view" badge reads the authoritative server count (`/rooms/summary/` — COUNT/AVG with the same geo filters), so it is never capped by list pagination
- **Distance markers** — every listing in a radius search shows `formatDistance` + walking time ("1.2 km away · ≈ 16 min walk") in its map popup and the side list, from the backend's `distance_km` annotation
- **Viewport bbox cache** — the refetch bbox is quantized to ~100 m, so micro-pans hit the React Query cache instead of firing duplicate API calls
- **Landmark layers** — toggle universities 🎓, metro stations 🚇, hospitals 🏥, markets 🛒, parks 🌳, mosques 🕌 and bus terminals 🚌 on/off as map layers (from `/rooms/landmarks/`); the everyday categories cluster into count bubbles at low zoom
- **Price heatmap** — green → amber → red circles scaled by rent, so expensive areas are visible at a glance
- **Map + list split view** — a viewport-synced sidebar lists the rooms on screen (promoted first, then by price); on mobile it becomes a bottom sheet
- Tapping a pin opens the room popup → full **RoomModal** (booking, chat, fraud badge, AI price insight)
- **Shareable map URLs** — the current viewport (center + zoom + radius search) is live-synced to the URL (`/map?center=23.81,90.41&zoom=12&r=23.78,90.40,2.0`), so you can copy the address and share an exact map view; the **Share** button copies the link, and opening a shared link restores the exact view, radius and area chips
- **Readable in both themes** — dark tiles are the CARTO CDN; if it's unreachable the map auto-falls back to dimmed OSM tiles (street labels stay legible), and the travel overlay + legend are styled for light _and_ dark

**Intelligent Map (Phase 7 v2) — Rental Decision Intelligence**

- **AI Smart Map Search** (🧠 "AI Map" button) — ask the map in Bangla, English or Banglish ("উত্তরায় ১২ হাজারের মধ্যে furnished room", "metro er kache room, Banani under 15k") and it parses the query into **hard filters** (area, budget, room type, amenities, metro proximity), flies to the matched area or metro station, updates the pins, and shows intent chips so you can see exactly what it understood — powered by the existing NL parser + gazetteer (`/rooms/map-intel/search/`), no hallucinated listings
- **Metro Commute Score** — every relevant listing carries a 0–100 transit-access score (walking time to the nearest MRT station, real curated station data) shown in the value-score chip
- **Commute mode** (🚇) — set a destination on the map (office / university / any point), and every visible listing gets a walking-time estimate ("🚶 8 min"); filter by max commute (15–60 min) — ETAs are honest straight-line estimates, labelled as such
- **Best Value Score** (⭐) — a transparent 0–100 server-side blend of price-fit vs the area market, amenities, listing quality, KYC verification, demand and metro access; each marker popup shows the score + transit factor, and the panel lists the top-value visible rooms
- **Area Intelligence panel** (🏛️ Areas) — tap an area chip for avg/median rent, listing counts, availability, 30-day demand (views/saves/bookings), metro access and price trend — all from real data, `—` where none exists; select up to 3 areas for a side-by-side **comparison table**
- **Affordability map** (💰 Budget) — drag a budget slider and see the **real % of currently listed rooms** per area that fit (green/amber/red bars) — a listing share, not an estimate
- **Ideal Area ranking** (⭐ Ideal Area) — budget + optional destination → the top areas ranked with the *why* ("100% of Mirpur listings fit your ৳10,000 budget · ~28 min commute (MRT estimate)")
- **Destination pin** — click the map to drop a teal destination flag for commute/ideal-area ranking; the pin is persisted in the shareable URL
- **Everything real** — no fabricated statistics: ETAs are labelled heuristics, transit ETA only exists along the MRT Line-6 corridor, and areas without data say "—"

See [`docs/INTELLIGENT_MAP.md`](docs/INTELLIGENT_MAP.md) (architecture) · [`docs/MAP_API.md`](docs/MAP_API.md) (endpoints) · [`docs/MAP_SCORING.md`](docs/MAP_SCORING.md) (formulas).

**Listing Location Picker (landlord)**

- **List a Room** now opens a proper form with a **map picker** — click the map to pin the exact listing location (or "Use my location")
- Coordinates are stored as `lat`/`lng`, powering the map view, geo search and price insight

**KYC Verification + Verified Landlord Badge**

- **Identity document upload** — landlords upload a NID or passport (image/PDF, 5 MB cap) from **Dashboard → KYC** (`KycCard`); uploads are stored server-side and **served through an auth-gated endpoint** (owner/admin only — the public media URL can never leak a document, and other users get a 404 so no existence leak)
- **Admin review panel** — pending applications queue (``GET /users/kyc/pending/``) with approve/reject; a decision flips `nid_verified`, **syncs every listing badge** via signals, resolves the pending documents, writes an **audit-log entry** (`kyc.approved` / `kyc.rejected`) and notifies the landlord — all inside one `transaction.atomic()` block
- **KYC audit trail** — Dashboard → KYC → History lists every decision (who, when, note) straight from the append-only audit log
- **Verified badge everywhere** — RoomCard pill, RoomModal, Roommates match cards, and **Chat** (shield next to a verified participant's name); verified-first ranking inside each tier
- **"Verified landlords only" filter** — one toggle on the Rooms page (`?verified=true`) narrows results to KYC-approved owners
- **E2E coverage** — upload → 403 for non-admin → queue → approve (badge flip + audit + notification + fraud signal clears) → reject with note → **reject → re-upload → approve full loop** (the landlord sees the reviewer's note on their rejected doc, re-submits, and the badge finally lands — the audit trail tells the whole story) → revoke flips back → privacy (404 for strangers) → file-type guard: 12 KYC tests
- **Rejection UX** — the dashboard KycCard shows a **"Why it was rejected"** banner with the reviewer's note (e.g. *"Blurry scan — please re-upload"*) plus the upload form, so the landlord knows exactly what to fix before re-submitting
- **Rejection email** — a rejection also sends a **branded transactional email** (`kyc_rejected` template) with the reviewer's note and a **direct re-upload CTA** that deep-links to the dashboard KYC tab, so the landlord can fix and resubmit without hunting through the app
- **KYC review SLA stats** — the admin panel now opens with a **queue-health strip**: pending applications (with the oldest-waiting age), average review time (all-time + this week), and a 7-day decision trend (`▲ +N / ▼ -N` vs last week), all from `GET /users/kyc/sla/` (admin-only)
- **SLA breach badges** — when a breach fires the strip grows **red alert chips** ("Application waiting >48h" / "Decisions down vs last week"), matching the flags the daily beat alert emails about — dashboard and alerts never disagree (same thresholds)
- **30-day decision trend chart** — the admin History tab now opens with a lightweight **dependency-free SVG chart**: daily decision counts (bars) + average review hours (line) over the last 30 days, bucketed server-side with `TruncDate`

**Engineering**

- **Coverage history per branch** — every PR and main push appends its own `history-<branch>.csv` + SVG chart to the `coverage-history` branch (viewable `index.html` linking all branches)
- 528 automated tests (334 backend + 194 frontend) · coverage gates (BE ≥50%, FE ≥55%)
- Ruff + ESLint + Prettier with husky/lint-staged pre-commit hooks
- GitHub Actions CI (backend, frontend, **live API contract check**, **frontend schema contract** (TS types vs OpenAPI), **schema-drift PR comment**, lint, coverage-summary PR comment, per-branch coverage history)
- Route-level code splitting (React.lazy) — smaller bundles

**Search & Discovery (Phase 11) — ✨ AI Smart Search**

- **AI Search toggle** — the Rooms page's search bar grows a gradient **✨ AI Search** button; flip it on and the box accepts *natural language*: "১০ হাজার এর মধ্যে uttara student room" is understood as **budget ≤ ৳10,000 in Uttara** (and "জুলাই move-in" as a July move-in date)
- **Bangla + English natural-language parser** (`rooms/nl_query.py`) — Bangla digits (০-৯), **number words** (দশ/বিশ/ত্রিশ… with হাজার/লাখ/কোটি multipliers — "দশ হাজার" → ৳10,000), ৳/টাকা/tk/taka, **area names in both scripts** (Uttara *and* উত্তরা, Dhanmondi *and* ধানমন্ডি — from the gazetteer's new Bangla aliases), room-type/gender words and month names in both scripts; the parsed budget/area/type/gender become **real filters**, and the list response carries an `nl_parsed` object
- **"AI understood" chips** — under the search bar the backend's interpretation renders as tappable-looking pills (`Budget ≤ ৳10,000` · `Uttara` · `move-in July`) so tenants see exactly what was understood
- **Hybrid neural semantic ranking** — smart search now blends **two relevance legs** with configurable weights (`SEMANTIC_SEARCH_WEIGHT=0.7` neural + `TFIDF_SEARCH_WEIGHT=0.3` lexical). The neural leg uses **pluggable embeddings** (`rooms/embedding_service.py`): a zero-dependency bilingual synonym-hash provider runs out of the box (no heavy deps — "affordable student room" finds "কম বাজেটের শিক্ষার্থীদের থাকার রুম" in both query directions), and installing the optional `sentence-transformers` package transparently upgrades it to real multilingual neural embeddings. If embeddings are unavailable, ranking degrades to the TF-IDF/LSA leg, then to keyword search — search never breaks
- **Typo tolerance** — smart search resolves same-script typos against a bounded area gazetteer: `mirpore`/`মিরপূর` still find Mirpur, `Dhanmondhi` finds Dhanmondi, `uttra` finds Uttara (`FUZZY_SEARCH_ENABLED`)
- **Bangla/English area aliases** — a single alias table (`rooms/area_aliases.py`) resolves every spelling of a place — `ধানমন্ডি`, `ধানমণ্ডি`, `Dhanmondi`, `Dhanmondhi`, `ধানমন্ডি ২৭`, `mirpur 10`, `উত্তরা সেক্টর ১০` — to its canonical area, shared by the NL parser and map gazetteer (`AREA_ALIAS_ENABLED`)
- **Personalized search re-ranking** — for signed-in tenants, smart-search results are re-ranked within the relevant pool by the user's preference profile (preferred area/type/budget/amenities — reused from the recommendation engine, no duplicated logic); cold-start users get plain relevance ranking and **hard filters (budget/area) always win** (`PERSONALIZED_SEARCH_ENABLED`, `PERSONALIZATION_WEIGHT=0.15`)
- **Price-anomaly badge** — room cards show a transparent price-vs-market chip (`↑ 25% above market`) computed from the existing fair-price prediction model, trained once per request and only rendered when the prediction is confident and the gap clears `PRICE_ANOMALY_THRESHOLD` (20%)
- **Debug ranking metadata** — `?debug_rank=1` (or `DEBUG=true`) attaches `rank_meta` (semantic/lexical/personalization/final scores per room) to the list response; never exposed to normal users
- **Personal ranking boost** — for signed-in tenants the default browse order floats rooms they recently viewed or wishlisted to the top (30-day window), layered under the paid-tier/verified ranking
- **Look-Alike Rooms (visual search)** — every RoomModal now shows a "Look-Alike Rooms" strip: rooms whose primary photo looks like the current one, via 64-bit **perceptual hashes (pHash)** computed with Pillow and cached in a new `RoomImageHash` table (mtime-keyed, so replaced photos re-hash automatically); `GET /rooms/{id}/similar-images/`
- **Dhaka coverage expanded** — the listing `Area` choices now span **20 areas** (Uttara, Tejgaon, Badda, Rampura, Banasree, Khilgaon, Motijheel, Old Dhaka, Bashundhara, Lalmatia, Shyamoli, Savar, Keraniganj, Tongi + the original 6) and the map gazetteer gained **40+ new streets/roads** (Panthapath, Bailey Road, Hatirjheel, Badda Link Road, Khilgaon Flyover, Uttara Sectors 10/12/14, Gulshan 1/2 circles, Jashimuddin Avenue …) plus 9 more universities (Jagannath, Dhaka Medical College, AUST, DIU, Stamford, UIU …) — all searchable from the map box and the NL parser
- **Bug fixes along the way** — the room list now sends the backend's `q` search param correctly (`params.search` → `params.q`), and the API client no longer yanks **anonymous** visitors to `/auth` when a public endpoint 401s (the bounce is now reserved for sessions that actually went stale) — regression-tested

**Core AI & Fraud Intelligence (Phase 11++) — Rentora Copilot, AI pricing v2, duplicate-image fraud**

- **🤖 Rentora Copilot** (`COPILOT_ENABLED`) — a floating conversational assistant (bottom-right, every page): ask in Bangla, English or Banglish ("Uttara-তে ১০ হাজারের মধ্যে furnished student room চাই") and it searches the **live** listings. Hybrid and free: intent parsing (reusing the NL parser + an amenity/property word table) feeds the existing search/ranking pipeline, and the reply is generated over the *retrieved* rows only — **it can never hallucinate a room, price or amenity**, and no LLM is required. Follow-up turns keep context ("শুধু furnished দেখাও" retains Uttara + budget via a session_id), listing cards open the full RoomModal, quick-reply chips are backend-generated (`POST /api/v1/copilot/chat/`, 60/hr throttle). See `docs/RENTORA_COPILOT.md`
- **🏷️ AI pricing suggestion v2** (`GET /pricing/suggestion/:id/`, owner/admin) — the fair-price model upgraded with **demand**: recommended price + range (rounded to ৳500), a 0–100 demand score from real engagement (views vs area peers, wishlist saves, booking requests, area heat), **estimated time-to-rent** from actual booking history (never fabricated — "Insufficient historical data" when there aren't 5 samples), composite confidence, and explainable reasons ("Similar Mirpur singles average ৳8,500"). Cached per room + market snapshot. Dashboard → **Insights** → **AI Price** expands the suggestion card with a **Use ৳12,500** button — the landlord always decides; nothing changes automatically. See `docs/AI_PRICING_V2.md`
- **🖼️ Cross-listing duplicate-image fraud detection** (`DUPLICATE_IMAGE_FRAUD_ENABLED`) — the pHash pipeline (already powering look-alike rooms) now feeds a 7th fraud detector: the same photo re-used across listings is flagged with contextual severity (same-owner agency posts → low; different owners → medium; different owner **and** area, or 3+ matches → high). Hex-prefix pre-filtering keeps scans from N×N; same-listing galleries and blank images are never flagged; the signal feeds the existing fraud score → search ranking, and the admin **Fraud Operations** panel shows matched-listing chips + similarity %. See `docs/DUPLICATE_IMAGE_FRAUD.md`

---

**Listing Intelligence (Phase 11+) — voice search, AI saved-search matching, listing quality, fraud-aware ranking**

- **🎤 Bangla voice search** — the search bar grows a microphone button (`VOICE_SEARCH_ENABLED`): the browser's **Web Speech API** transcribes Bangla / Banglish / English naturally ("উত্তরা ১০ হাজারের মধ্যে রুম" → `?q=`), and the transcript flows straight into the existing NL parser + semantic ranking — no new NLP pipeline, **no audio ever stored or uploaded** (only the transcript). Unsupported browsers hide the button; permission-denied shows a friendly hint; text search always works (`useVoiceSearch` hook, states: idle/listening/processing/denied/unsupported/error)
- **🧠 AI saved-search matcher** (`SAVED_SEARCH_AI_MATCHING_ENABLED`) — saved-search alerts upgraded from "new listing" to **"Highly relevant room found in Uttara"** with *why it matched* reasons (✓ matches your area ✓ within budget ✓ similar to rooms you viewed). Two-stage pipeline: **hard filters always gate first** (area/budget/type/gender — a Dhanmondi room can never match a Uttara search), then a weighted relevance score (`area/price/room-type/semantic/preference/quality`, weights + `SAVED_SEARCH_MATCH_THRESHOLD=0.75` configurable). Alerts fire in-app from a **room create/price-change event task** and the daily digest, deduplicated by a **cooldown** (`SAVED_SEARCH_COOLDOWN_HOURS`); **price-drop alerts** (≥ `PRICE_DROP_NOTIFICATION_THRESHOLD` 10%) ride on the new `RoomPriceHistory` table written by a post-save signal
- **✨ Listing quality score** (`LISTING_QUALITY_SCORE_ENABLED`) — every listing gets a transparent **0–100 completeness score** (basic info 20 / description 20 / photos 20 / location 15 / amenities 15 / pricing 10 — weights configurable) with **actionable suggestions** ("Add 3 more photos", "Description is too short…", "Add nearby landmark information"). Shown as a quality chip on the room detail page and a **per-listing Quality column in the landlord Insights dashboard** with a tap-for-suggestions popover, plus an **Avg Listing Quality card** on the landlord overview. It's *not* a valuation and *not* a fraud score — every point is explainable
- **🛡️ Fraud-aware search ranking** (`FRAUD_AWARE_RANKING_ENABLED`) — smart-search results are **demoted by the existing fraud engine's risk score** (one query, no re-scan): high-risk listings sink below clean ones of equal relevance (`FRAUD_RANKING_PENALTY_WEIGHT=0.20`), and critical-risk handling follows the existing moderation flow — ranking **never hides or deletes** a listing. Risk never overrides explicit user intent (hard filters → relevance → personalization → quality → fraud), and internal detector evidence is never exposed to normal users (admin dashboard unchanged)
- **Search pipeline now**: query → normalization → area-alias expansion → hard filters → lexical + semantic legs → personalization → quality + fraud secondary signals → final ranking → API response
- **Copilot retrieval reuses the same pipeline** — hard filters (budget/area/type/gender/amenities) gate first, then hybrid ranking — so a Copilot answer and the Rooms page agree by construction

---

## 🗺️ Delivery Roadmap

> Tracked like a product backlog — every shipped phase is checked off.

| Phase     | Scope                                                                                                                                                | Status               |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| **1–2**   | React prototype with mock data                                                                                                                       | ✅ Shipped           |
| **2.5**   | Frontend refactor — Vite, TS strict, Tailwind, Zustand, React Query, shadcn/ui                                                                       | ✅ Shipped           |
| **3**     | Django backend — 10+ apps, JWT auth, full REST API, frontend integration                                                                             | ✅ Shipped           |
| **4**     | Real-time chat (Django Channels, typing, read receipts, file upload) + real-time notifications                                                       | ✅ Shipped           |
| **5**     | Payments — SSLCommerz + bKash, refunds, PDF receipts, invoices, security deposits, webhook audit                                                     | ✅ Shipped           |
| **6**     | AI — recommendation engine (content/collaborative/hybrid) + price insight + fair-price prediction                                                    | ✅ Shipped           |
| **Bonus** | Roommate matching (profile + scoring + request flow)                                                                                                 | ✅ Shipped           |
| **Bonus** | Fraud engine (6 detectors, auto-scan, review queue)                                                                                                  | ✅ Shipped           |
| **Bonus** | Paid listing tiers (Free/Featured/Premium monetization)                                                                                              | ✅ Shipped           |
| **Bonus** | Two-factor authentication (email OTP, password-gated enable)                                                                                         | ✅ Shipped           |
| **Bonus** | KYC verification + verified-landlord badge + document upload + audit trail                                                                           | ✅ Shipped           |
| **Bonus** | 2FA recovery codes (10 one-time backups) + email-verified enable                                                                                     | ✅ Shipped           |
| **Bonus** | Passkeys / WebAuthn (passwordless login, conditional UI)                                                                                             | ✅ Shipped           |
| **Bonus** | Geo backend (bbox / radius / landmark queries)                                                                                                       | ✅ Shipped           |
| **7**     | Map (MapLibre GL, clustering, split view, radius + travel overlay, street search, metro routes, room-count API, directions + metro ETA + area chips) | ✅ Shipped           |
| **8**     | Docker Compose + production deployment + HTTPS                                                                                                       | ⏳ Next — CI/CD done |
| **9**     | Reliability & observability — Sentry, JSON logs, Celery + beat, branded emails, audit log, backups, KYC SLA alerts + trend chart                    | ✅ Shipped           |
| **10**    | Growth & personalization — browser push, search v2 (full-text + saved searches), similar-rooms AI, referral program, wishlist sharing, landlord insights, reviews v2 | ✅ Shipped |
| **11**    | Search & Discovery v2 — ✨ AI smart search (Bangla+English NL parser, semantic ranking, visual search), Dhaka expansion                              | ✅ Shipped           |
| **11+**   | Listing Intelligence — 🎤 Bangla voice search, 🧠 AI saved-search matcher + price-drop alerts, ✨ listing quality score, 🛡️ fraud-aware ranking       | ✅ Shipped           |
| **11++**  | Core AI & Fraud — 🤖 Rentora Copilot, 🏷️ AI pricing suggestion v2 (demand/time-to-rent), 🖼️ cross-listing duplicate-image fraud detection | ✅ Shipped |
| **7 v2**   | Intelligent Map — 🧠 AI map search, 🚇 metro commute score + commute mode, ⭐ best-value scores, 🏛️ area intelligence + comparison, 💰 affordability map, ideal-area ranking | ✅ Shipped |
| **7 v3**   | Map Intelligence v3 — 🌙 dark-map fix + 🌑 layer contrast QA, 👆 interactive university/metro/heatmap/isochrone clicks, 🔗 map↔list sync, 🔗 room deep links, 🏙️ structured Dhaka hierarchy + area boundary polygons, 🏥 expanded landmark layer (hospitals/markets/parks/mosques/bus terminals, clustered) | ✅ Shipped |
| **12 P0**  | Progressive Web App — 📱 installable manifest + maskable icons, native install CTA, standalone mode, safe SW caching, update + offline UX, shortcuts | ✅ Shipped |
| **12 P1**  | Offline & polish — 🔌 offline search over cached public listings, background sync (offline action replay), periodic refresh, splash screens, dark icon, iOS install hint, Lighthouse audit | ✅ Shipped |
| **12**     | Trust & Safety V2 — two-sided marketplace integrity: 🪪 tenant KYC + verified-tenant badge, 🛡️ chat safety engine, 🚩 report/block, 🖼️ photo + review moderation, ⚖️ disputes + deposit protection, 🎛️ admin Trust & Safety Operations Center + audit trail | ✅ Shipped |
| **12.6**   | Tier-1 Quick Wins — 💬 chat message search + edit/delete (audited), 📧 saved-search email digest, 🚦 report rate-limit + duplicate guard, ⚡ semantic search cache, 🛡️ CSP headers + security.txt + dependency bump audit | ✅ Shipped |
| **12.7**   | Tier-2 Upgrades — 🧠 AI chat-safety classifier (learned layer, human fallback), 📊 self-hosted analytics + conversion funnel, 🖼️ photo manipulation/watermark detection (ELA), 🗺️ OSRM road-network ETA, 🦠 ClamAV upload scan, 🪪 KYC auto pre-screening, ⬆️ react-router v7 | ✅ Shipped |
| **12.8**   | Tier-3 Upgrades — 🤖 RAG Copilot (listing-grounded Q&A, zero hallucination), 🌐 full EN⇄BN UI toggle, 🧠 production-grade neural embeddings (disk-persisted matrix + prebuild command), 🧪 E2E expansion (trust-flow + map), 👤 tenant behavioral trust signals (completed bookings) | ✅ Shipped |
| **12.9**   | Tier-4 Upgrades — 🤝 AI Rental Advisor, 💬 AI Negotiation Assistant, 📄 AI Agreement Checker, 🏠 Landlord Copilot, 📊 AI Property Comparison, 📈 Demand Forecasting, 🔔 Smart AI Alerts, 🧠 hosted neural embeddings (HF endpoint), 🪪 automated KYC pre-verification, 🧪 browser-level Playwright E2E | ✅ Shipped |
| **12.10**  | Tier-5 Upgrades — 📈 conversion funnel fully wired (booking_confirmed + payment_completed server-side), 🖼️ photo forensics v2 (text-overlay + tiled-watermark detection), 💹 per-listing price recommendation (demand forecast + market + interest), 👁️ Copilot image understanding (statistical photo answers), ✍️ AI listing draft (one-click title/description/amenities) | ✅ Shipped |
| **13**     | Reach — 📱 SMS OTP phone sign-in (BD market, gateway-gated), 🟢 WhatsApp listing share + AI share summary, 🗺️ per-area SEO landing pages + sitemap, ⚡ Lighthouse performance gate in CI | ✅ Shipped |
| **14**     | AI v3 Vision & Content — 👁️ photo intelligence (caption/palette/observations from actual photos), ✍️ AI draft title + description from photos, 🏷️ suggested amenity tags (review-then-apply), 📷 AI image search ("upload a photo, find rooms that look like it") with match scores | ✅ Shipped |
| **15**     | Monetization 2.0 — 💳 subscriptions + entitlements (landlord SaaS), 🧾 idempotent revenue ledger + commission engine, 🏢 corporate housing (accounts / bulk booking / invoices), 🏅 verified broker network (attribution / payouts), 🛍️ add-on services marketplace (orders + AI cross-sell), 🛡️ insurance & credit partnerships, 🎛️ admin revenue & payout centre | ✅ Shipped |
| **16**     | Hardening & Scale — 🧠 embeddings + pgvector (vendor-guarded), 🚩 feature flags + A/B experiments, 🖼️ image pipeline/CDN (WebP variants, private storage), 🔴 Redis hardening (leases, locks, timeouts), ⚡ rate limiting + abuse prevention, ⏱️ Celery reliability (retry, ack-late, time limits), 🏥 `/health/` liveness, 📋 X-Request-ID correlation | ✅ Shipped |
| **17**     | Graph & Deep Trust — 🕸️ scam-network graph (PostgreSQL nodes/edges, community detection), 🪪 KYC liveness + face-match (pluggable providers), 📷 photo-geo authenticity (GPS mismatch), 🕵️ fake-review detection (trust scoring + anomalies), 📊 model drift monitoring (metrics + retrain requests), 🔐 PII masking + privacy layer, 🧩 shared provider abstraction (BaseProvider/Registry) | ✅ Shipped |
| **18.1**   | AI Intelligence Foundation — 🧠 AI feature registry (central registry + provider tracking), 📊 execution telemetry (latency/tokens/cost/confidence per request), 🏥 provider health monitoring (p95/p99 latency, success rates, auto-degradation), 💰 cost estimation engine (OpenAI + Anthropic pricing), 🔌 TelemetryMixin (drop-in for BaseProvider), 🎛️ admin API (7 endpoints, staff-only) | ✅ Shipped |
| **18.2**   | AI Intelligence Foundation — 📝 prompt registry (versioned templates, activate/deactivate/rollback), 🔗 feature flag integration (`is_feature_available` checks registry + Django flags), 🌱 `register_ai_features` seeds 30 real features, 🎛️ admin API expanded to 18 endpoints | ✅ Shipped |
| **18.3**   | AI Evaluation Framework — 📏 evaluation metrics (deterministic/heuristic/LLM-judge), 📊 golden datasets (versioned, publishable), 🔬 evaluator abstraction (26 built-in: search/classification/fraud/LLM/general/prediction), 🧪 evaluation runs (async Celery, per-case results), 📈 model/prompt comparison, 🚨 regression detection (threshold-based), 🎛️ admin API (17 eval endpoints) | ✅ Shipped |
| **18.4**   | AI Intelligence Dashboard + Alerts — 📊 cached admin dashboard (overview/features/models/providers/cost/performance/errors/quality/drift/prompts), 🔔 configurable alert rules with anti-noise (dedup/cooldown/consecutive), 🔁 alert lifecycle (acknowledge/resolve/suppress, audited), 🔔 in-app admin notifications + deep links, ⚙️ beat tasks (rule evaluation 5 min, cache warm 30 min), 🎛️ admin UI (Dashboard → AI tab, 11 sub-views + rule editor) | ✅ Shipped |

---

## ✨ Features

**For Tenants**

- Browse and search verified room listings across Dhaka
- AI-powered room recommendations based on budget, area, and preferences
- Advanced filters (area, type, price range, amenities, gender preference)
- Geo search — filter by map viewport (`bbox`), radius around a point, or proximity to landmarks/metro stations
- **Interactive map** (MapLibre GL) — price pins, radius search, university/metro layers, price heatmap
- Wishlist rooms for later
- Book rooms with one click
- Real-time chat with landlords (WebSocket — typing, read receipts, file upload)
- **Roommate matching** — find compatible flatmates by budget, area, lifestyle, and gender preference
- **Tenant identity verification** — verify once with a NID/passport and carry the **✓ Identity Verified badge** (identity only — never a behavioral or financial guarantee)
- **Chat safety** — every message is screened for payment-redirect scams, phishing links and impersonation; risky messages show warnings and blocked ones are replaced with a safety notice
- **Report & block** — report a user or a specific message (scam, harassment, fake listing, payment fraud…) and block/unblock to close a conversation both ways
- **Dispute resolution** — open a structured dispute on an approved booking (deposit, property condition, cancellation…) with evidence, admin review and a clear outcome
- Dashboard with booking stats and notifications

**For Landlords**

- Create and manage room listings with multiple images
- Receive booking requests with approve/reject workflow
- Get notified on new bookings and reviews
- **Fraud protection** — every listing is auto-scanned on creation; flagged listings show an "under review" badge
- **Paid listing tiers** — promote a listing to **Featured** (৳199/30 days) or **Premium** (৳499/30 days) via SSLCommerz/bKash to rank higher in search and show a badge; expired promotions auto-revert to Free
- **KYC verification** — verified landlords carry a trust badge (RoomCard, RoomModal, Roommates, Chat) and rank first; tenants can filter to verified owners only
- **Verified tenants in chat** — identity-verified tenants carry the ✓ badge in chat, booking requests and roommate matches, so you know who's inquiring
- **Report & dispute tools** — report problem users/messages and respond to booking disputes with evidence before a resolution is decided
- Dashboard with revenue stats, ratings, listing analytics, and fraud risk cards with one-click re-scan

**Platform Features**

- JWT authentication (register/login/refresh/logout) with **unique-email enforcement**
- Paid listing tiers (monetization) with server-side pricing and premium-first search ordering
- Real-time notifications (booking updates, reviews, roommate requests, fraud flags)
- Review system with verified stay badges — reviews and photos are auto-moderated (spam, duplicate-image, contact harvesting) with an admin approval queue
- 6-detector fraud engine
- **Trust & Safety Operations Center** — unified admin console (tenant KYC queue, chat-safety feed, report tickets, photo/review moderation, disputes + deposit decisions) with a read-only audit trail
- Responsive design (mobile, tablet, desktop) + dark mode
- API documentation (Swagger UI + ReDoc)

---

## 🏗️ Tech Stack

### Frontend

| Technology              | Purpose                                    |
| ----------------------- | ------------------------------------------ |
| React 18                | UI framework                               |
| TypeScript (strict)     | Type safety                                |
| Vite                    | Build tool                                 |
| TailwindCSS v4          | Styling                                    |
| shadcn/ui               | Component library                          |
| React Router v6         | Client-side routing                        |
| Zustand                 | Client state management                    |
| TanStack Query          | Server state + caching                     |
| Axios                   | HTTP client with interceptors              |
| React Hook Form + Zod   | Form validation                            |
| Motion                  | Entrance/exit animation                    |
| MapLibre GL JS          | Interactive map (markers, layers, heatmap) |
| zxcvbn-ts               | Password entropy + strength                |
| Pwned Passwords (HIBP)  | k-anonymity breach lookup                  |
| Sonner                  | Toast notifications                        |
| Vitest                  | Unit tests + coverage                      |
| @simplewebauthn/browser | Passkey ceremony client                    |

### Backend

| Technology                    | Purpose                                 |
| ----------------------------- | --------------------------------------- |
| Django 5.2                    | Web framework                           |
| Django REST Framework         | REST API                                |
| Django Channels               | WebSocket support                       |
| Daphne                        | ASGI server                             |
| SimpleJWT                     | JWT authentication                      |
| dj-rest-auth + django-allauth | Auth endpoints                          |
| django-filter                 | API filtering                           |
| drf-spectacular               | OpenAPI docs                            |
| bleach                        | Input sanitization                      |
| difflib                       | Similarity detection (fraud engine)     |
| PostgreSQL 16                 | Production database                     |
| SQLite                        | Development database                    |
| Redis                         | Channel layer + caching + Celery broker |
| Celery                        | Async task queue + beat scheduler       |
| Sentry (sentry-sdk)           | Error tracking (backend + frontend)     |
| py_webauthn                   | WebAuthn/FIDO2 server-side (passkeys)   |
| scikit-learn                  | TF-IDF + LSA semantic search            |
| sentence-transformers *(optional)* | Real multilingual neural embeddings (upgrades the built-in lite provider) |
| Pillow (pHash)                | Visual similarity (look-alike rooms)    |
| pywebpush                     | Browser push notifications (VAPID)      |
| pytest / unittest             | Backend tests                           |

---

## 🖥️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend (React SPA)                    │
│  Pages ── hooks (TanStack Query) ── services ── Axios API      │
│  Zustand stores ── WebSocket client ── service worker (push)   │
│  MapLibre GL (map) · WebAuthn (passkeys) · zxcvbn (strength)   │
└───────────────┬──────────────────────────────┬────────────────┘
                │ HTTP /api/v1/*                │ WS /ws/chat/*
┌───────────────▼──────────────────────────────▼────────────────┐
│                    Django (ASGI — Daphne)                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────────────────────┐ │
│  │ JWT Auth   │ │ REST apps  │ │ Channels consumer (chat)   │ │
│  │ 2FA +      │ │ rooms,     │ │ + presence + notifications │ │
│  │ passkeys   │ │ bookings,  │ └────────────────────────────┘ │
│  │ (WebAuthn) │ │ payments,  │ ┌────────────────────────────┐ │
│  └────────────┘ │ roommates, │ │ Fraud engine (6 detectors)│ │
│  ┌────────────┐ │ fraud, AI, │ └────────────────────────────┘ │
│  │ Exception  │ │ saved-     │ ┌────────────────────────────┐ │
│  │ envelope   │ │ searches…  │ │ Hybrid semantic search      │ │
│  └────────────┘ └────────────┘ │ (embeddings + TF-IDF/LSA) · │ │
│  ┌────────────┐                 │ NL parser · aliases · pHash │ │
│  │ Audit log  │                 └────────────────────────────┘ │
│  │ (append-   │  ┌──────────────────────────────────────────┐ │
│  │ (append-   │  │ Celery + Beat (push, alerts, re-scan)    │ │
│  │ only)      │  └──────────────────────────────────────────┘ │
│  └────────────┘  Sentry (errors) · JSON logs · email templates│
└───────────────┬──────────────────────────────────────────────┘
                │ ORM / cache / channel layer
        ┌───────▼──────────┐   ┌──────────┐   ┌──────────────┐
        │  SQLite (dev) /  │   │  Redis   │   │ SSLCommerz / │
        │  PostgreSQL 16   │   │ (cache,  │   │ bKash gateways│
        └──────────────────┘   │ channel) │   └──────────────┘
                               └──────────┘
```

---

## 📁 Project Structure

```
Rentora/
├── frontend/                  # React SPA
│   ├── src/
│   │   ├── components/        # UI components (Navbar, RoomCard, ChatWindow, PromoteModal, TierBadge…)
│   │   │   └── ui/            # shadcn/ui primitives
│   │   ├── pages/             # Route pages (Home, Rooms, Map, Chat, Dashboard, Roommates, Auth)
│   │   ├── services/          # API service layer (auth, rooms, bookings, roommates, fraud, payments…)
│   │   ├── hooks/             # TanStack Query hooks
│   │   ├── stores/            # Zustand stores (ui, wishlist, notifications)
│   │   ├── context/           # React context (AppContext for auth)
│   │   ├── types/             # TypeScript type definitions
│   │   ├── config/            # Environment config
│   │   └── styles/            # TailwindCSS config + global styles
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── backend/                   # Django REST API
│   ├── config/                # Project config (settings, urls, asgi, exceptions, middleware)
│   │   └── settings/          # Split settings (base, dev, prod)
│   ├── users/                 # Custom User model + auth (unique email enforced)
│   ├── rooms/                 # Room listings + images + geo queries + listing tiers
│   ├── bookings/              # Bookings + Reviews + signals
│   ├── wishlist/              # Wishlist toggle
│   ├── notifications/         # Auto-notifications + API
│   ├── dashboard/             # Aggregated stats endpoint
│   ├── chat/                  # Real-time chat (Channels, WebSocket, presence)
│   ├── payments/              # SSLCommerz + bKash, refunds, invoices, receipts, tier upgrades
│   ├── recommendations/       # Content-based + collaborative + hybrid engine
│   ├── pricing/               # Market stats + price insight + fair-price prediction
│   ├── roommates/             # Roommate profiles + weighted matching algorithm
│   ├── fraud/                 # 6-detector fraud engine + auto-scan + review queue
│   ├── manage.py
│   └── requirements.txt
│
└── docs/                      # Documentation + screenshot tooling
```

---

## 🧪 Quality Engineering

Quality is enforced **in CI and at commit time** — style or coverage drift fails the pipeline automatically.

### Automated tests (1058 total)

| Suite             | Count | Gate                                      |
| ----------------- | ----- | ----------------------------------------- |
| Backend (Django)  | 716   | ✅ passing · coverage ≥ 50% lines |
| Frontend (Vitest) | 342   | ✅ passing · coverage ≥ 55% lines         |

```bash
# Backend
cd backend && venv/Scripts/python.exe -m coverage run manage.py test && venv/Scripts/python.exe -m coverage report

# Frontend
cd frontend && npx vitest run --coverage
```

### Lint & format

```bash
# Backend (ruff)
cd backend
venv/Scripts/python.exe -m ruff check .          # lint
venv/Scripts/python.exe -m ruff check --fix .    # auto-fix
venv/Scripts/python.exe -m ruff format .         # format
venv/Scripts/python.exe -m ruff format --check . # verify

# Frontend (ESLint + Prettier)
cd frontend
npm run lint
npm run format
npm run format:check
```

### Pre-commit hooks (husky + lint-staged)

Installed automatically by `npm install` (`prepare` script). On every commit it runs **only on staged files**:

| Staged file                        | Runs                               |
| ---------------------------------- | ---------------------------------- |
| `backend/**/*.py`                  | `ruff check --fix` + `ruff format` |
| `frontend/**/*.{ts,tsx}`           | `prettier --write` + `eslint`      |
| `frontend/**/*.{css,json,md,html}` | `prettier --write`                 |

If a check fails, the commit is **blocked** — fix and commit again (bypass with `git commit --no-verify` only when intentional).

### CI/CD (GitHub Actions)

| Workflow               | Job                                                         | Runs on         |
| ---------------------- | ----------------------------------------------------------- | --------------- |
| `ci.yml`               | Backend — Django tests + coverage gate                      | every push / PR |
| `ci.yml`               | Frontend — Vitest + coverage + `npm run build`              | every push / PR |
| `ci.yml`               | API contract — boots a server + runs the live endpoint suite vs the docs reference (**status codes + deep JSON schema + request-body contracts + OpenAPI path cross-check**; response/request contracts are **auto-generated from the live OpenAPI schema** at runtime — `docs/tools/api-verify.py`) | every push / PR |
| `ci.yml`               | **Frontend contract** — regenerates TS types from the live OpenAPI schema (`openapi-typescript`) and typechecks the hand-written wire types (`services/mappers.ts`) against them via `src/lib/schemaContract.ts` — a backend field rename/removal/type change fails the PR | every push / PR |
| `ci.yml`               | **Schema drift** — diffs the PR head's OpenAPI schema against the base branch and posts a sticky PR comment listing every endpoint/field contract change (`docs/tools/schema-drift.py`; doc-only changes ignored) | PRs |
| `security.yml`         | **Security** — `pip-audit` (dependency advisories, hard-fail), Bandit (MEDIUM+ static analysis, hard-fail), Django `check --deploy`, security regression tests (upload validation / admin-only fraud / IDOR / KYC ownership), `npm audit --audit-level=high` (hard-fail) and a **gitleaks** secret scan — all with least-privilege `contents: read` | every push / PR |
| `ci.yml`               | Lint — ruff + ESLint + Prettier                             | every push / PR |
| `coverage-summary.yml` | Posts a coverage **PR comment** (badge + file-level detail) | PRs             |
| `ci.yml` `coverage-history` job | Appends per-branch coverage history (`history-<branch>.csv` + SVG chart) to the `coverage-history` branch | pushes to main **and** PRs (same-repo; fork PRs skip) |

---

## 🚀 Getting Started

### Quick Start (TL;DR)

```bash
git clone https://github.com/SadmaFaahiim/Rentora.git && cd Rentora

# Backend → http://localhost:8000
cd backend
python -m venv venv && venv\Scripts\activate   # (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_rooms                  # 20+ rooms + demo landlords (password: demo12345)
python manage.py runserver

# Frontend → http://localhost:3000 (new terminal)
cd ../frontend
npm install
npm run dev
```

> 💡 `seed_rooms` also creates the demo users below — sign in with any username + `demo12345`.
> No `.env` files are required; sensible defaults work out of the box.
>
> **Optional — real neural embeddings:** smart search works out of the box with the built-in
> zero-dependency lite provider. To upgrade to true multilingual transformer embeddings,
> install the optional package: `pip install sentence-transformers` (a multi-hundred-MB
> download incl. PyTorch) — the app detects it automatically and uses
> `SEMANTIC_EMBEDDING_MODEL` (default: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`).

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Seed sample data (rooms + demo landlords)
python manage.py seed_rooms

# Scan all rooms with the fraud engine (optional)
python manage.py scan_rooms

# Create admin user
python manage.py createsuperuser

# Start server
python manage.py runserver

# Backup the database (SQLite copy or pg_dump; prunes old backups)
python ../scripts/backup_db.py --keep 14
```

Backend runs at `http://localhost:8000`

**Celery (optional, async mode)** — with no broker configured, tasks run eagerly
(synchronously) so nothing extra is needed locally. To run a real worker + beat
schedule, start Redis and set `CELERY_BROKER_URL=redis://localhost:6379/0` in
`backend/.env`, then:

```bash
celery -A config worker -l info
celery -A config beat -l info
```

**Error tracking** — set `SENTRY_DSN` (backend `.env`) and `VITE_SENTRY_DSN`
(frontend `.env`) to enable Sentry; leaving them unset keeps everything working
with no events sent. See `docs/ops/backup-restore.md` for the backup/restore
runbook.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env file
echo "VITE_API_BASE_URL=http://localhost:8000/api/v1" > .env

# Start dev server
npm run dev
```

Frontend runs at `http://localhost:3000`

---

## 📡 API Endpoints

### Authentication

| Method | Endpoint                                  | Auth   | Description                                                                                              |
| ------ | ----------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------- |
| POST   | `/api/v1/auth/register/`                  | Public | Register (email must be unique)                                                                          |
| POST   | `/api/v1/auth/login/`                     | Public | Login with email or username (returns JWT)                                                               |
| POST   | `/api/v1/auth/logout/`                    | Auth   | Logout (blacklist token)                                                                                 |
| POST   | `/api/v1/auth/token/refresh/`             | Public | Refresh access token                                                                                     |
| GET    | `/api/v1/auth/user/`                      | Auth   | Get current user profile                                                                                 |
| PATCH  | `/api/v1/auth/user/`                      | Auth   | Update profile                                                                                           |
| POST   | `/api/v1/auth/otp/verify/`                | Public | Finish 2FA login: exchange (challenge, code) for JWTs; pass `recovery_code` instead to use a backup code |
| POST   | `/api/v1/auth/otp/resend/`                | Public | Re-send the one-time code (cooldown-guarded)                                                             |
| POST   | `/api/v1/auth/otp/toggle/`                | Auth   | Disable 2FA, or begin enabling (password → emailed code)                                                 |
| POST   | `/api/v1/auth/otp/confirm-enable/`        | Auth   | Confirm the emailed code → 2FA on + one-time recovery codes                                              |
| POST   | `/api/v1/auth/passkey/register/begin/`    | Auth   | Registration options for the browser ceremony                                                            |
| POST   | `/api/v1/auth/passkey/register/complete/` | Auth   | Verify + store the new passkey (public key only)                                                         |
| POST   | `/api/v1/auth/passkey/login/begin/`       | Public | Authentication options + `challenge_id` (conditional UI)                                                 |
| POST   | `/api/v1/auth/passkey/login/complete/`    | Public | Verify the assertion → JWTs (or pending OTP for 2FA)                                                     |
| POST   | `/api/v1/auth/sms/request/`               | Public | Request an SMS OTP for a phone number (503 while SMS is disabled)                                        |
| POST   | `/api/v1/auth/sms/verify/`                | Public | Verify the SMS code → JWTs (new numbers auto-register)                                                   |

### Rooms

| Method    | Endpoint                   | Auth   | Description                                       |
| --------- | -------------------------- | ------ | ------------------------------------------------- |
| GET       | `/api/v1/rooms/`           | Public | List rooms (filter/search/sort/geo/tier ordering) |
| GET       | `/api/v1/rooms/:id/`       | Public | Room detail                                       |
| POST      | `/api/v1/rooms/`           | Auth   | Create listing                                    |
| PUT/PATCH | `/api/v1/rooms/:id/`       | Owner  | Update listing                                    |
| DELETE    | `/api/v1/rooms/:id/`       | Owner  | Delete listing                                    |
| GET       | `/api/v1/rooms/landmarks/` | Public | List landmarks (for `near_landmark`)              |
| GET       | `/api/v1/rooms/summary/`   | Public | COUNT/AVG for the current viewport (map badge)    |
| GET       | `/api/v1/rooms/map-intel/stats/`         | Public | Per-area rent/demand/metro stats (intelligent map)          |
| GET       | `/api/v1/rooms/map-intel/commute/`       | Public | Walking/driving/MRT-corridor ETA between two points        |
| GET       | `/api/v1/rooms/eta/`                     | Public | OSRM road-network ETA (car/cng/bus) with heuristic fallback |
| GET       | `/api/v1/rooms/map-intel/value/`         | Public | Transparent 0–100 value scores for room ids                |
| GET       | `/api/v1/rooms/map-intel/affordability/` | Public | % of listed rooms per area within a budget                 |
| GET       | `/api/v1/rooms/map-intel/ideal-areas/`   | Public | Ranked areas for budget + destination, with reasons        |
| GET       | `/api/v1/rooms/map-intel/search/`        | Public | Natural-language map search (Bangla/Banglish) → intent + rooms + fly-to target |
| GET       | `/api/v1/rooms/geocode/?q=` | Public | Geocode a street/area (gazetteer + Nominatim)    |
| GET       | `/api/v1/rooms/insights/`  | Auth (own listings) | Per-listing engagement + price vs area stats      |
| POST      | `/api/v1/rooms/bulk/`      | Auth  | Bulk-create listings (JSON array body)            |
| GET       | `/api/v1/rooms/tier-catalog/` | Public | Tier pricing + benefits (drives Promote UI)     |
| GET       | `/api/v1/rooms/:id/similar-images/` | Public | Rooms whose primary photo looks like this one (pHash) |
| GET       | `/api/v1/rooms/:id/price-recommendation/` | Owner/Admin | Per-listing raise/hold/lower price suggestion (demand + market + interest) |
| POST      | `/api/v1/rooms/generate-description/` | Auth | Deterministic AI draft — title + description + amenity tags for a listing |
| POST      | `/api/v1/rooms/:id/vision/analyze/` | Owner/Admin | Run + store photo intelligence (caption, palette, observations, suggested tags) |
| GET       | `/api/v1/rooms/:id/vision/` | Owner/Admin | The stored vision analysis (404 before first run) |
| POST      | `/api/v1/rooms/:id/vision/description/` | Owner/Admin | AI draft title + description + tags **from the listing's photos** |
| POST      | `/api/v1/rooms/vision/search/` | Public (30/min) | Upload a photo → look-alike listings with `match_score` + reasons |

**Text filters:** `?area=Dhanmondi&room_type=studio&price__gte=5000&price__lte=15000&is_available=true&q=cozy&ordering=-price&owner=3`

**Smart search:** `?q=১০ হাজার এর মধ্যে uttara student room&smart=1` — natural-language parsing (budget/area/type/gender become filters), **hybrid ranking** over the filtered pool (neural embeddings + TF-IDF/LSA, with typo-tolerant area aliases and per-user personalization for signed-in tenants), and an `nl_parsed` block describing what was understood. List cards also carry an optional `price_anomaly` object (`{predicted_price, difference_percentage, direction, badge}`) when the listing's price is confidentially ≥20% above/below the predicted market price.

**Geo filters:**

- `bbox=min_lng,min_lat,max_lng,max_lat` — map viewport (leaflet `getBounds()`)
- `near_lat=23.75&near_lng=90.39&radius_km=2` — radius around a point (nearest-first)
- `near_landmark=mirpur-10-metro&radius_km=3` — radius around a named landmark/metro station

### Bookings

| Method | Endpoint                | Auth | Description                     |
| ------ | ----------------------- | ---- | ------------------------------- |
| GET    | `/api/v1/bookings/`     | Auth | My bookings (tenant + landlord) |
| POST   | `/api/v1/bookings/`     | Auth | Create booking request          |
| PATCH  | `/api/v1/bookings/:id/` | Auth | Update status (role-gated)      |

### Reviews

| Method | Endpoint                    | Auth   | Description                               |
| ------ | --------------------------- | ------ | ----------------------------------------- |
| GET    | `/api/v1/reviews/?room=:id` | Public | Reviews for a room                        |
| POST   | `/api/v1/reviews/`          | Auth   | Create review (requires approved booking) |
| GET    | `/api/v1/reviews/summary/?room=:id` | Public | Rating breakdown (5★ histogram + avg + verified badges) |

### Wishlist

| Method | Endpoint                   | Auth | Description                  |
| ------ | -------------------------- | ---- | ---------------------------- |
| GET    | `/api/v1/wishlist/`        | Auth | My wishlisted rooms          |
| POST   | `/api/v1/wishlist/toggle/` | Auth | Toggle wishlist (`room_id` body) |
| GET    | `/api/v1/wishlist/share-info/` | Auth | Get my public share token + link |
| GET    | `/api/v1/wishlist/share/:token/` | Public | Public read-only wishlist (no personal info, 404 on bad token) |

### Notifications

| Method | Endpoint                               | Auth | Description      |
| ------ | -------------------------------------- | ---- | ---------------- |
| GET    | `/api/v1/notifications/`               | Auth | My notifications |
| PATCH  | `/api/v1/notifications/:id/`           | Auth | Mark as read     |
| POST   | `/api/v1/notifications/mark-all-read/` | Auth | Mark all read    |
| GET    | `/api/v1/notifications/unread-count/`  | Auth | Unread count     |
| POST   | `/api/v1/notifications/push/subscribe/` | Auth | Register a browser push subscription (VAPID) |

### Saved Searches

| Method   | Endpoint                     | Auth | Description                          |
| -------- | ---------------------------- | ---- | ------------------------------------ |
| GET      | `/api/v1/saved-searches/`    | Auth | My saved searches                    |
| POST     | `/api/v1/saved-searches/`    | Auth | Save the current filter set          |
| DELETE   | `/api/v1/saved-searches/:id/` | Auth | Delete a saved search                |
| POST     | `/api/v1/saved-searches/:id/check/` | Auth | Manual "check now" for new matches |

> A daily Celery beat task (`check_saved_searches`) notifies you when a **new** matching listing appears.
> A second daily beat task (`send_saved_search_digests`) emails you one branded summary when your saved
> searches matched new listings (opt out with `digest_emails_enabled`).

### Users / Referral

| Method | Endpoint              | Auth | Description                          |
| ------ | --------------------- | ---- | ------------------------------------ |
| GET    | `/api/v1/users/referral/` | Auth | My referral code, invite link + who joined |

### Dashboard

| Method | Endpoint                   | Auth | Description                    |
| ------ | -------------------------- | ---- | ------------------------------ |
| GET    | `/api/v1/dashboard/stats/` | Auth | User stats (tenant + landlord) |

### Chat

| Method   | Endpoint                           | Auth | Description                                   |
| -------- | ---------------------------------- | ---- | --------------------------------------------- |
| GET/POST | `/api/v1/chat/rooms/`              | Auth | List / create chat rooms                      |
| GET      | `/api/v1/chat/rooms/:id/messages/` | Auth | Messages in a room (`?search=` filters content; deleted messages excluded) |
| POST     | `/api/v1/chat/rooms/:id/messages/` | Auth | Send a message                                |
| PATCH    | `/api/v1/chat/rooms/:id/messages/:mid/` | Auth | Edit your own text message (audited)      |
| DELETE   | `/api/v1/chat/rooms/:id/messages/:mid/` | Auth | Soft-delete your own message (audited)    |
| GET      | `/api/v1/chat/online-status/`      | Auth | Online status of users                        |
| POST     | `/api/v1/chat/upload/`             | Auth | Upload a chat attachment                      |
| WS       | `/ws/chat/:room_id/`               | Auth | Real-time chat socket (typing, read receipts) |

### Payments

| Method | Endpoint                                             | Auth   | Description                     |
| ------ | ---------------------------------------------------- | ------ | ------------------------------- |
| POST   | `/api/v1/payments/initiate/`                         | Auth   | Initiate a payment (SSLCommerz) |
| POST   | `/api/v1/payments/bkash/initiate/`                   | Auth   | Initiate a bKash payment        |
| POST   | `/api/v1/payments/bkash/callback/`                   | Public | bKash gateway callback          |
| POST   | `/api/v1/payments/sslcommerz/success\|fail\|cancel/` | Public | SSLCommerz callbacks            |
| GET    | `/api/v1/payments/`                                  | Auth   | My payment history              |
| GET    | `/api/v1/payments/:id/`                              | Auth   | Payment detail / receipt        |
| POST   | `/api/v1/payments/:id/refund/`                       | Auth   | Request a refund                |
| GET    | `/api/v1/payments/summary/`                          | Auth   | Payment summary                 |

### Recommendations

| Method | Endpoint                           | Auth | Description                 |
| ------ | ---------------------------------- | ---- | --------------------------- |
| GET    | `/api/v1/recommendations/?limit=N` | Auth | Hybrid room recommendations |
| GET    | `/api/v1/recommendations/similar/:id/` | Public | Content-based similar rooms (modal carousel, match % + reasons) |

### Pricing (AI)

| Method | Endpoint                                           | Auth   | Description                          |
| ------ | -------------------------------------------------- | ------ | ------------------------------------ |
| POST   | `/api/v1/pricing/predict/`                         | Auth   | Predict fair price for a new listing |
| GET    | `/api/v1/pricing/insight/:room_id/`                | Public | Price insight vs market for a room   |
| GET    | `/api/v1/pricing/suggestion/:room_id/`             | Owner/Admin | AI pricing suggestion v2 — range, demand, time-to-rent, confidence |
| GET    | `/api/v1/pricing/market-stats/?area=X&room_type=Y` | Public | Raw market stats                     |

### Copilot

| Method | Endpoint                          | Auth   | Description                                                                        |
| ------ | --------------------------------- | ------ | ---------------------------------------------------------------------------------- |
| POST   | `/api/v1/copilot/chat/`           | Public | Conversational discovery — search mode (intent + listings) or `listing_id`-grounded RAG Q&A over one listing |
| GET    | `/api/v1/copilot/listing/:id/`    | Public | Grounded public fact card for one listing (the RAG source document)                |
| GET    | `/api/v1/copilot/share-summary/<id>/` | Public | Deterministic share-ready listing summary (WhatsApp share text)                |
| POST   | `/api/v1/copilot/advisor/`        | Public | AI Rental Advisor — budget + income → grounded budget plan (rent cap, areas, monthly breakdown) |
| POST   | `/api/v1/copilot/negotiate/`      | Public | AI Negotiation Assistant — comparable-price counter-offer + draft EN/BN message  |
| POST   | `/api/v1/copilot/agreement-check/`| Public | AI Rental Agreement Checker — one-sided clauses, advance-payment risk, missing BN-standard fields |
| POST   | `/api/v1/copilot/landlord/`       | Auth (owner/admin) | Landlord Copilot — price position, quality score, occupancy risk for one owned listing |
| GET    | `/api/v1/rooms/compare/?ids=1,2`  | Public | AI Property Comparison — 2–5 rooms side-by-side with per-area value        |
| GET    | `/api/v1/analytics/forecast/`     | Public | Demand forecasting for area + room type (powers alerts & insights)          |
| GET    | `/api/v1/notifications/smart/`    | Auth   | Smart AI Alerts — inbox re-ranked by transparent priority (0–100) + reason  |

### Roommates

| Method   | Endpoint                                 | Auth     | Description                                  |
| -------- | ---------------------------------------- | -------- | -------------------------------------------- |
| GET/PUT  | `/api/v1/roommates/profile/`             | Auth     | Get / upsert my roommate profile             |
| GET      | `/api/v1/roommates/matches/`             | Auth     | Best-first scored match suggestions          |
| GET/POST | `/api/v1/roommates/requests/`            | Auth     | My requests (incoming + outgoing) / send one |
| POST     | `/api/v1/roommates/requests/:id/action/` | Receiver | Approve or reject a request                  |

### Fraud Detection

| Method | Endpoint                                   | Auth        | Description                                                            |
| ------ | ------------------------------------------ | ----------- | ---------------------------------------------------------------------- |
| GET    | `/api/v1/fraud/rooms/:room_id/status/`     | Public      | Public badge data (drives "under review" badge)                        |
| GET    | `/api/v1/fraud/reports/`                   | Auth        | Reports (owner: own rooms; admin: all) — filter by `status`/`severity` |
| POST   | `/api/v1/fraud/rooms/:room_id/scan/`       | Owner/Admin | Re-run the detector on a room                                          |
| POST   | `/api/v1/fraud/reports/:report_id/review/` | Admin       | Mark reviewed / dismissed                                              |

### Listing Tiers (Monetization)

| Method | Endpoint                                  | Auth   | Description                                                      |
| ------ | ----------------------------------------- | ------ | ---------------------------------------------------------------- |
| GET    | `/api/v1/rooms/tier-catalog/`             | Public | Tier pricing + benefits catalog (drives the Promote UI)          |
| POST   | `/api/v1/payments/tier-upgrade/initiate/` | Owner  | Start a promotion payment (Featured/Premium; amount server-side) |

Tiers: **Free** (default) → **Featured** (৳199/30d: boosted above free, badge, Home "Featured Rooms") → **Premium** (৳499/30d: top of search, gold badge, priority in AI recommendations). Expired promotions revert to Free automatically (`expire_listings` management command + query-time `effective_tier`).

### Monetization 2.0 (Revenue)

**Subscriptions** — `/api/v1/subscriptions/`

| Method | Endpoint                                  | Auth   | Description                                                         |
| ------ | ----------------------------------------- | ------ | ------------------------------------------------------------------- |
| GET    | `/subscriptions/plans/`                   | Public | Active plan catalog (pricing server-side)                           |
| GET    | `/subscriptions/subscription/me/`         | Auth   | My subscription + entitled features                                 |
| POST   | `/subscriptions/subscription/me/`         | Auth   | Start plan checkout (SSLCommerz/bKash) — returns the gateway URL    |
| POST   | `/subscriptions/subscription/:id/cancel/` | Auth   | Cancel at period end                                                |
| POST   | `/subscriptions/subscription/:id/renew/`  | Auth   | Start a renewal checkout                                            |

**Revenue & payouts** — `/api/v1/monetization/`

| Method | Endpoint                                      | Auth   | Description                                              |
| ------ | --------------------------------------------- | ------ | -------------------------------------------------------- |
| GET    | `/monetization/revenue/dashboard/`            | Admin  | Revenue by scope, gross/platform, MRR, pending obligations, recent ledger/commissions/payouts |
| GET    | `/monetization/payouts/requests/`             | Admin  | Payout request queue (`?status=`)                        |
| POST   | `/monetization/payouts/:id/decision/`         | Admin  | Approve / reject a payout (balance-safe)                 |
| POST   | `/monetization/payouts/:id/mark-paid/`        | Admin  | Mark an approved payout as paid (offline settlement)     |

**Broker network** — `/api/v1/brokers/`

| Method | Endpoint                       | Auth  | Description                                            |
| ------ | ------------------------------ | ----- | ------------------------------------------------------ |
| POST   | `/brokers/register/`           | Auth  | Submit broker profile + first verification             |
| GET/PUT| `/brokers/profile/`            | Broker| Broker profile                                          |
| GET    | `/brokers/dashboard/`          | Broker| Balance, pending/paid summary, recent commissions      |
| GET    | `/brokers/commissions/`        | Broker| Own commissions (`?status=`)                           |
| GET    | `/brokers/payouts/`            | Broker| Own payout requests                                    |
| POST   | `/brokers/payouts/request/`    | Broker| Request a payout of earned commissions                 |
| POST   | `/brokers/:id/review/`         | Admin | Review a broker verification                           |

**Corporate housing** — `/api/v1/corporate/`

| Method | Endpoint                                | Auth        | Description                                    |
| ------ | --------------------------------------- | ----------- | ---------------------------------------------- |
| GET/POST | `/corporate/accounts/`               | Auth        | List / create corporate accounts               |
| GET    | `/corporate/accounts/:id/`              | Member/Admin| Account detail                                 |
| GET/POST | `/corporate/accounts/:id/members/`   | Owner/Admin | List / invite members by email                 |
| POST   | `/corporate/bulk-booking/`              | Owner/Admin | Book a room for several members (partial success) |
| GET    | `/corporate/invoices/`                  | Auth        | Own corporate invoices                         |
| GET    | `/corporate/admin/`                     | Company admin | Overview + account approvals                   |

**Add-on services marketplace** — `/api/v1/marketplace/`

| Method | Endpoint                                 | Auth    | Description                                        |
| ------ | ---------------------------------------- | ------- | -------------------------------------------------- |
| POST   | `/marketplace/providers/register/`       | Auth    | Register a service-provider business               |
| GET    | `/marketplace/providers/me/`             | Provider| My provider profile                                |
| GET    | `/marketplace/services/`                 | Auth    | Active service catalog (`?category=`)              |
| GET    | `/marketplace/services/:id/`             | Auth    | Service detail                                     |
| GET/POST | `/marketplace/orders/`                 | Auth    | My orders / place an order                         |
| POST   | `/marketplace/orders/:id/action/`        | Provider| Confirm / cancel / complete an order               |
| GET    | `/marketplace/recommend/?booking_id=`    | Auth    | AI cross-sell recommendations after booking        |

**Insurance & credit partnerships** — `/api/v1/partner-services/`

| Method | Endpoint                                          | Auth   | Description                                    |
| ------ | ------------------------------------------------- | ------ | ---------------------------------------------- |
| GET    | `/partner-services/insurance/products/`           | Public | Insurance product catalog                      |
| GET/POST | `/partner-services/insurance/quotes/`           | Auth   | My quotes / request a quote                    |
| POST   | `/partner-services/insurance/quotes/:id/action/`  | Partner| Issue / decline / cancel a quote               |
| GET    | `/partner-services/credit/eligibility/`           | Auth   | Renter credit eligibility (pre-approved limit) |

### KYC Verification

| Method | Endpoint                                                      | Auth        | Description                                                          |
| ------ | ------------------------------------------------------------- | ----------- | -------------------------------------------------------------------- |
| GET    | `/api/v1/users/kyc/documents/`                                | Auth        | My KYC documents (admin: all)                                        |
| POST   | `/api/v1/users/kyc/documents/`                                | Auth        | Upload a NID/passport document (multipart, 5 MB cap)                 |
| GET    | `/api/v1/users/kyc/documents/:id/file/`                       | Owner/Admin | **Auth-gated document file** — strangers get 404 (no existence leak) |
| GET    | `/api/v1/users/kyc/pending/`                                  | Admin       | Pending applications queue                                           |
| POST   | `/api/v1/users/kyc/:user_id/review/`                          | Admin       | Approve/reject (badge sync + audit log + notification, atomic)       |
| GET    | `/api/v1/users/kyc/audit/`                                    | Admin       | Full KYC decision trail (who/when/note from the audit log)           |
| GET    | `/api/v1/users/kyc/sla/`                                      | Admin       | Review-queue health: pending count, avg review hours, 7-day trend, **breach flags** (`oldest_pending` / `trend_negative`) and 30-day daily trend (`trend_30d`) |
| GET    | `/api/v1/rooms/?verified=true`                                | Public      | Only rooms owned by KYC-approved landlords                           |
| GET    | `/api/v1/users/tenant-kyc/`                                  | Tenant      | My tenant verification status                                       |
| POST   | `/api/v1/users/tenant-kyc/`                                  | Tenant      | Submit tenant identity document (multipart)                         |
| GET    | `/api/v1/users/tenant-kyc/pending/`                          | Admin       | Pending tenant-verification queue                                   |
| POST   | `/api/v1/users/tenant-kyc/:user_id/review/`                  | Admin       | Approve / reject / request resubmission (audited + notified)        |

### Trust & Safety V2 (Moderation, Disputes, Audit)

| Method | Endpoint                                                | Auth   | Description                                                          |
| ------ | ------------------------------------------------------- | ------ | -------------------------------------------------------------------- |
| GET    | `/api/v1/chat/safety/events/`                           | Admin  | Chat-safety assessments feed (metadata only, no raw content)         |
| POST   | `/api/v1/chat/reports/`                                 | Auth   | Report a user or message (7 categories)                              |
| GET    | `/api/v1/chat/reports/admin/`                           | Admin  | Moderation tickets queue (`?status=`)                                |
| POST   | `/api/v1/chat/reports/:report_id/action/`               | Admin  | Dismiss / warn / restrict / suspend / escalate (audited)             |
| POST   | `/api/v1/chat/block/`                                   | Auth   | Block a user (closes the conversation both ways)                     |
| GET    | `/api/v1/chat/blocked/`                                 | Auth   | My blocked users                                                     |
| DELETE | `/api/v1/chat/block/:user_id/`                          | Auth   | Unblock                                                              |
| GET    | `/api/v1/moderation/overview/`                          | Admin  | Moderation queue counts (reviews + photos)                           |
| GET    | `/api/v1/moderation/reviews/`                           | Admin  | Review-moderation queue (`?status=`)                                 |
| POST   | `/api/v1/moderation/reviews/:id/action/`                | Admin  | Approve / reject a review (audited + notified)                       |
| GET    | `/api/v1/moderation/photos/`                            | Admin  | Photo-moderation queue (`?status=`)                                  |
| POST   | `/api/v1/moderation/photos/:id/action/`                 | Admin  | Approve / reject a photo (audited + notified)                        |
| GET/POST | `/api/v1/disputes/`                                    | Auth   | My disputes / open one on an approved booking                        |
| GET    | `/api/v1/disputes/:id/`                                 | Participant | Dispute detail (participants only — IDOR-guarded)                    |
| POST   | `/api/v1/disputes/:id/evidence/`                        | Participant | Add evidence (text / photo / document)                               |
| GET    | `/api/v1/disputes/admin/`                               | Admin  | All disputes (`?status=`)                                            |
| POST   | `/api/v1/disputes/admin/:id/action/`                    | Admin  | Transition / resolve / reject + deposit decision (release/refund)    |
| GET    | `/api/v1/audit/`                                        | Admin  | Read-only audit trail (`?prefix=` filters by domain)                 |
| POST   | `/api/v1/analytics/events/`                             | Any    | First-party event capture (auth-optional, bounded, throttled)        |
| GET    | `/api/v1/analytics/summary/`                            | Admin  | Analytics snapshot: totals, top events/pages, conversion funnel      |

### Documentation

| Endpoint          | Description           |
| ----------------- | --------------------- |
| `/api/v1/docs/`   | Swagger UI            |
| `/api/v1/redoc/`  | ReDoc                 |
| `/api/v1/schema/` | OpenAPI schema (YAML) |

> 📖 Deeper reading: [`docs/architecture.md`](docs/architecture.md) (system design, data model, flows, deployment) · [`docs/api-reference.md`](docs/api-reference.md) (full endpoint reference + curl examples) · [`docs/ops/backup-restore.md`](docs/ops/backup-restore.md) (backup/restore runbook) · [`docs/RENTORA_COPILOT.md`](docs/RENTORA_COPILOT.md) (Copilot architecture, API, config) · [`docs/AI_PRICING_V2.md`](docs/AI_PRICING_V2.md) (pricing suggestion v2) · [`docs/DUPLICATE_IMAGE_FRAUD.md`](docs/DUPLICATE_IMAGE_FRAUD.md) (duplicate-image detector) · [`docs/INTELLIGENT_MAP.md`](docs/INTELLIGENT_MAP.md) + [`docs/MAP_API.md`](docs/MAP_API.md) + [`docs/MAP_SCORING.md`](docs/MAP_SCORING.md) (intelligent map v2) · [`docs/VOICE_SEARCH_PLAYBOOK.md`](docs/VOICE_SEARCH_PLAYBOOK.md) (voice search) · [`docs/LIVE_VERIFICATION.md`](docs/LIVE_VERIFICATION.md) (verified feature matrix) · [`docs/PWA.md`](docs/PWA.md) (PWA architecture, manifest, SW strategy, install/update/offline behavior) · [`docs/phase-12-trust-safety-v2.md`](docs/phase-12-trust-safety-v2.md) (Phase 12 Trust & Safety V2) · [`docs/TENANT_KYC.md`](docs/TENANT_KYC.md) + [`docs/CHAT_SAFETY.md`](docs/CHAT_SAFETY.md) (tenant KYC + chat safety) · [`docs/tier2-upgrades.md`](docs/tier2-upgrades.md) (AI chat-safety classifier, self-hosted analytics, photo forensics, OSRM ETA, ClamAV, KYC auto pre-screen, react-router v7) · [`docs/tier3-upgrades.md`](docs/tier3-upgrades.md) (RAG Copilot listing mode, EN⇄BN i18n, production-grade embeddings, E2E expansion, tenant trust signals) · [`docs/tier4-upgrades.md`](docs/tier4-upgrades.md) (AI advisor, negotiation assistant, agreement checker, landlord copilot, property comparison, demand forecast, smart alerts, hosted embeddings, KYC auto pre-screen, Playwright E2E) · [`docs/tier5-upgrades.md`](docs/tier5-upgrades.md) (funnel analytics wiring, photo forensics v2, price recommendation, Copilot image understanding, AI listing draft) · [`docs/phase-15-monetization-2.0.md`](docs/phase-15-monetization-2.0.md) (Phase 15 Monetization 2.0 — subscriptions, revenue ledger, brokers, corporate, marketplace, insurance/credit) · [`docs/phase-15-communication-trust-ai.md`](docs/phase-15-communication-trust-ai.md) (Phase 15 Communication & Trust AI — chat translation, support copilot, KYC OCR, review summary, market report, fraud rings) · [`docs/phase-16-hardening.md`](docs/phase-16-hardening.md) (Phase 16 Hardening & Scale — embeddings, feature flags, image pipeline, Redis, rate limiting, Celery) · [`docs/phase-17-final-report.md`](docs/phase-17-final-report.md) (Phase 17 Graph & Deep Trust — scam-network graph, KYC liveness, photo-geo, fake-review detection, model drift, PII masking)

---

## 🔐 Security

- JWT authentication with access/refresh token rotation
- **Unique email enforced at the API and database layers** (registration, admin, seed scripts all covered)
- Rate limiting (auth: 10/hr per IP, anon: 100/hr, user: 1000/hr, payment initiation: 5/hr)
- Input sanitization via bleach on all user-generated text
- CORS configured (dev: all origins, prod: pinned domains)
- Custom error handler with consistent JSON envelope
- Production security headers (HSTS, XSS filter, content-type nosniff)
- **Append-only audit log** for sensitive actions (fraud-report reviews, 2FA changes) — immutable in the admin, so an audit trail cannot be rewritten
- **Error tracking** via Sentry (backend + frontend) and **structured JSON logs** (`JSON_LOGS=True`) so incidents are visible and searchable
- **Defensive fraud scanning** — a detector or queue failure can never break room creation; detector errors are isolated and logged
- **Fraud engine** auto-scans every new listing — flagged listings go into an admin review queue
- **Password hygiene on register** — zxcvbn-ts entropy scoring rejects trivially guessable passwords with actionable warnings; HaveIBeenPwned k-anonymity check warns when the chosen password appears in known data breaches (nothing but a 5-char hash prefix ever leaves the device)
- **Two-factor authentication (email OTP)** — challenge codes are stored hashed, TTL-bounded (10 min), attempt-limited (5 → lock) and cooldown-guarded; the login endpoint never returns tokens for a 2FA account until the code is verified
- **2FA enable is email-verified** — password + emailed code are both required before `otp_enabled` flips, and **recovery codes** (10, hashed, single-use) are minted at that moment; disabling deletes them
- **Passkeys** — public-key only storage, sign-counter replay protection, conditional UI on login
- **KYC document privacy** — identity documents are served through an **auth-gated endpoint** (owner/admin only); the public media URL can never expose a document, and non-owners get a 404 so even file existence is hidden
- **Automated security CI** (`.github/workflows/security.yml`) — `pip-audit` dependency advisories (hard-fail), Bandit MEDIUM+ static analysis (hard-fail), Django `check --deploy`, security regression tests (upload validation / admin-only fraud / IDOR / KYC ownership), `npm audit --audit-level=high` (hard-fail) and a **gitleaks** secret scan — running on every push/PR with least-privilege permissions

## 🔑 Passkeys / WebAuthn — Shipped

Passwordless sign-in is live — the phishing-resistant successor to passwords + OTP:

| Aspect              | TOTP/OTP (email)                                | Passkeys (WebAuthn)                             |
| ------------------- | ----------------------------------------------- | ----------------------------------------------- |
| UX friction         | Open email, copy 6-digit code                   | One tap / biometric (Touch ID, Windows Hello)   |
| Phishing resistance | Vulnerable (codes can be typed into fake sites) | **Immune** — bound to the exact origin (`rpId`) |
| Secrets             | Shared secret stored server-side                | Server stores **public keys only**              |

**Implemented with** `py_webauthn` (webauthn 3.x, Duo Labs) server-side + `@simplewebauthn/browser` client-side. Four DRF endpoints: `passkey/register/begin` → `passkey/register/complete` (JWT-authed), `passkey/login/begin` → `passkey/login/complete` (issues JWTs). Conditional UI (`mediation: 'conditional'`) surfaces passkeys in the browser's native autofill; a manual **"Sign in with a passkey"** button is the fallback. Register/revoke from Dashboard → Security → Passkeys.

**Gotchas handled:** WebAuthn requires a secure origin (`localhost` is fine; IP addresses are not); frontend/backend should share a registrable domain in production (e.g. `app.example.com` + `api.example.com` with `rpId: example.com`); an `AbortController` cancels a pending conditional ceremony when the user submits the password form.

---

## 📱 Progressive Web App — Shipped

**Install Rentora** as a native-feeling app — desktop (Chrome/Edge) and mobile (Android; iOS via **Add to Home Screen**) — without a separate codebase:

- **Installable** — `manifest.webmanifest` (standalone display, brand `#ea580c` theme), 192/512 standard + **maskable** icons, Apple-touch + favicon set; validated in CI against the built app
- **Polite install prompt** — no surprise popups: a subtle **"Install app"** button in the navbar shows the browser's native prompt; disappears after install, cools off for a week after dismissal
- **App-like window** — standalone mode keeps routing, auth, the map (with shareable URL sync), voice search, Copilot, saved searches and both dashboards working exactly as in the browser; deep links open the right page
- **Safe offline + offline search** — a graceful "You're offline" banner, never fake data; the app shell is cached while **API/auth/admin/fraud/payment data is never cached**. When offline, the Rooms page searches within the cached **public** listings (client-side filters, "showing N cached" pill) and queued actions (wishlist) replay on reconnect via background sync
- **Fresh updates** — a "A new version of Rentora is available **[Refresh] [Later]**" banner when a new build deploys
- **Native polish** — Apple splash screens, dark maskable icon, iOS "Add to Home Screen" hint, and the brand flag rendered as an **inline SVG** (no emoji-rendering issues)
- **Shortcuts** — right-click / long-press the installed icon → Search Rooms · Explore Map · Post Listing

See [`docs/PWA.md`](docs/PWA.md) for the manifest, icon system, service-worker strategy, update/offline behavior, security review and browser support.

---

## 🧑‍💻 Demo Users

> Seed the database first (see [Getting Started](#-getting-started)), then sign in with any of these accounts. Password for all: **`demo12345`**

| Role        | Username        | What to explore                                                                                         |
| ----------- | --------------- | ------------------------------------------------------------------------------------------------------- |
| 🏠 Landlord | `rahim.hossain` | Roommate matches (Sabbir 87%, Nadia 76%), room listing, **Paid Tiers** (Dashboard → Listings → Promote) |
| 🏠 Landlord | `nadia.islam`   | Shared Premium Gulshan listing                                                                          |
| 🏠 Landlord | `sabbir.rahman` | Student Room Azimpur listing                                                                            |
| 🏠 Landlord | `farhana.akter` | Modern Studio Mirpur listing                                                                            |
| 🏠 Landlord | `tanvir.islam`  | Fraud dashboard (Executive Single Banani + re-scan)                                                     |
| 🏠 Landlord | `demo.promoter` | **Fresh FREE listing** — try the Promote flow end-to-end                                                |
| 🏠 Landlord | `kyc.demo`      | **Unverified landlord** — Dashboard → KYC: upload a document, then watch an admin approve it and the **verified badge** appear on your listing + chat                                      |
| 🏠 Landlord | `kyc.rejected`  | **Rejected KYC demo** — Dashboard → KYC shows the **"Why it was rejected"** banner with the reviewer's note and a ready re-upload form                                  |

**Tips**

- All seeded accounts are **landlords** — to explore the **tenant** side (browse, search, wishlist, book, chat), just **register a fresh account** from the login page (unique email required) or use the platform anonymously for browsing.
- **Admin:** run `python manage.py createsuperuser` then open `http://localhost:8000/admin/` — the fraud review queue, KYC review, and the append-only audit trail live there.
- Sign in with the **username** (e.g. `rahim.hossain`) **or** the email address (e.g. `rahim.hossain@rentora.com`) — both work.
- `rahim.hossain` has a roommate profile — log in and open **Roommates** to see live match scores.
- `tanvir.islam` has listings — open **Dashboard → Fraud** to see the risk cards and try **Re-scan**.
- `kyc.rejected` starts with a rejected document — open **Dashboard → KYC** to see the rejection note, then upload a clear copy to restart the review loop.
- **Try 2FA:** Dashboard → **Two-Factor Authentication** → **Enable 2FA** (current password → emailed code → save your **recovery codes**). Next sign-in asks for the emailed code (or a recovery code). In development the code prints to the backend console; in production it goes to the account's email.
- **Try passkeys:** Dashboard → Security → **Passkeys** → **Register a passkey** (your device's biometric/PIN), then sign out and use the login page's passkey autofill or the **"Sign in with a passkey"** button.

> 💡 Screenshots can be regenerated with [`docs/tools/capture-screenshots.mjs`](docs/tools/capture-screenshots.mjs) — it drives headless Chrome, mints demo tokens via Django, and saves fresh PNGs into `docs/screenshots/`.

---

## 🖼️ Screenshots

### Phase-wise gallery

Every shipped phase with its captured screenshots (all in `docs/screenshots/`):

| Phase | Feature | Screenshot(s) |
| ----- | ------- | ------------- |
| 4 | Real-time chat | [`voice-search.png`](docs/screenshots/voice-search.png) (voice search in chat) |
| 5 | Payments & security deposit | [`deposit-protection.png`](docs/screenshots/deposit-protection.png) |
| 6 | AI recommendations & price insight | [`listing-quality.png`](docs/screenshots/listing-quality.png) · [`price-anomaly.png`](docs/screenshots/price-anomaly.png) · [`pricing-suggestion.png`](docs/screenshots/pricing-suggestion.png) |
| 7 | Map + Intelligent Map (v2/v3) | [`map-view.png`](docs/screenshots/map-view.png) · [`map-view-dark.png`](docs/screenshots/map-view-dark.png) · [`map-intel-ai-search.png`](docs/screenshots/map-intel-ai-search.png) · [`map-intel-areas.png`](docs/screenshots/map-intel-areas.png) · [`map-intel-affordability.png`](docs/screenshots/map-intel-affordability.png) · [`map-ux-light-default.png`](docs/screenshots/map-ux-light-default.png) · [`map-ux-dark-state.png`](docs/screenshots/map-ux-dark-state.png) |
| 9 | Reliability & observability | [`kyc-sla.png`](docs/screenshots/kyc-sla.png) · [`kyc-trend-chart.png`](docs/screenshots/kyc-trend-chart.png) |
| 10 | Growth & personalization | [`phase10-dashboard-growth.png`](docs/screenshots/phase10-dashboard-growth.png) · [`phase10-insights.png`](docs/screenshots/phase10-insights.png) · [`phase10-saved-search.png`](docs/screenshots/phase10-saved-search.png) · [`saved-search-match.png`](docs/screenshots/saved-search-match.png) |
| 11 | AI search + Copilot + fraud | [`phase11-ai-search.png`](docs/screenshots/phase11-ai-search.png) · [`copilot.png`](docs/screenshots/copilot.png) · [`duplicate-image-fraud.png`](docs/screenshots/duplicate-image-fraud.png) · [`fraud-admin.png`](docs/screenshots/fraud-admin.png) |
| 12 | Trust & Safety V2 | [`tenant-kyc-upload.png`](docs/screenshots/tenant-kyc-upload.png) · [`tenant-kyc-pending.png`](docs/screenshots/tenant-kyc-pending.png) · [`verified-tenant-badge.png`](docs/screenshots/verified-tenant-badge.png) · [`report-block.png`](docs/screenshots/report-block.png) · [`chat-safety-feed.png`](docs/screenshots/chat-safety-feed.png) · [`moderation-reviews.png`](docs/screenshots/moderation-reviews.png) · [`moderation-photos.png`](docs/screenshots/moderation-photos.png) · [`dispute-admin.png`](docs/screenshots/dispute-admin.png) · [`trust-center.png`](docs/screenshots/trust-center.png) · [`audit-trail.png`](docs/screenshots/audit-trail.png) |
| 12.6–12.8 | Tier-1/2/3 upgrades (chat edit/delete, analytics, RAG Copilot, EN⇄BN UI, trust signals) | [`phase12.8-copilot-listing-qa.png`](docs/screenshots/phase12.8-copilot-listing-qa.png) · [`phase12.8-lang-toggle.png`](docs/screenshots/phase12.8-lang-toggle.png) · [`phase12.8-completed-bookings.png`](docs/screenshots/phase12.8-completed-bookings.png) |
| 12.9 | Tier-4 upgrades (AI tools, comparison, landlord copilot, smart alerts) | [`phase12.9-ai-tools-advisor.png`](docs/screenshots/phase12.9-ai-tools-advisor.png) · [`phase12.9-compare.png`](docs/screenshots/phase12.9-compare.png) · [`phase12.9-landlord-copilot.png`](docs/screenshots/phase12.9-landlord-copilot.png) · [`phase12.9-smart-alerts.png`](docs/screenshots/phase12.9-smart-alerts.png) |
| 12.10 | Tier-5 upgrades (funnel analytics, price recommendation, Copilot vision, AI draft) | [`tier5-price-recommendation.png`](docs/screenshots/tier5-price-recommendation.png) · [`tier5-ai-draft.png`](docs/screenshots/tier5-ai-draft.png) · [`tier5-copilot-photos.png`](docs/screenshots/tier5-copilot-photos.png) |
| 13 | Reach (SMS OTP, WhatsApp share, area SEO) | [`phase13-area-page.png`](docs/screenshots/phase13-area-page.png) · [`phase13-whatsapp-share.png`](docs/screenshots/phase13-whatsapp-share.png) · [`phase13-sms-login.png`](docs/screenshots/phase13-sms-login.png) |
| 14 | AI v3 Vision & Content (photo intelligence, AI image search) | [`phase14-vision-panel.png`](docs/screenshots/phase14-vision-panel.png) · [`phase14-image-search-dialog.png`](docs/screenshots/phase14-image-search-dialog.png) · [`phase14-image-search-results.png`](docs/screenshots/phase14-image-search-results.png) |
| 15 | Communication & Trust AI + Monetization 2.0 | [`phase15-market-report.png`](docs/screenshots/phase15-market-report.png) · [`phase15-chat-translate.png`](docs/screenshots/phase15-chat-translate.png) · [`phase15-copilot-support.png`](docs/screenshots/phase15-copilot-support.png) · [`phase15-copilot-tts.png`](docs/screenshots/phase15-copilot-tts.png) · [`phase15-kyc-ocr.png`](docs/screenshots/phase15-kyc-ocr.png) · [`phase15-review-ai-summary.png`](docs/screenshots/phase15-review-ai-summary.png) · [`phase15-price-v2.png`](docs/screenshots/phase15-price-v2.png) · [`phase15-fraud-rings.png`](docs/screenshots/phase15-fraud-rings.png) |
| 16 | Hardening & Scale (similar-rooms embeddings, pgvector) | [`phase16-similar-rooms.png`](docs/screenshots/phase16-similar-rooms.png) |
| 17 | Graph & Deep Trust (fraud graph admin) | [`phase17-fraud-graph-admin.png`](docs/screenshots/phase17-fraud-graph-admin.png) |
| 18 | AI Intelligence (dashboard + alerts) | [`phase18-ai-dashboard.png`](docs/screenshots/phase18-ai-dashboard.png) |
| 19.1 | Property Intelligence (admin inspector) | [`phase19-1-property-intelligence.png`](docs/screenshots/phase19-1-property-intelligence.png) |
| 19.2 | AI Rental Agent (grounded chat + bookmark consent) | [`phase19-2-rental-agent.png`](docs/screenshots/phase19-2-rental-agent.png) |

Below, the detailed phase-by-phase screenshots.

---

**Interactive Map (MapLibre GL)** — street-search autocomplete, price marker pins, clustering, split-view list, radius search, walking travel-time overlay & MRT Line 6 corridor:

<img width="1440" alt="Interactive Map" src="docs/screenshots/map-view.png" />

**Interactive Map — dark theme** (auto fallback to dimmed OSM tiles keeps the map readable):

<img width="1440" alt="Interactive Map Dark" src="docs/screenshots/map-view-dark.png" />

**Intelligent Map — AI Smart Search (Phase 7 v2)** — ask the map in Bangla/Banglish ("উত্তরায় ১২ হাজারের মধ্যে furnished room"): the parsed intent chips (area · budget · amenities), live matching rooms and the map flying to the result:

<img width="1440" alt="Intelligent Map AI Search" src="docs/screenshots/map-intel-ai-search.png" />

**Intelligent Map — Area Intelligence** — tap an area for avg/median rent, availability, 30-day demand, metro access and price trend (real data only; select up to 3 to compare):

<img width="1440" alt="Intelligent Map Areas" src="docs/screenshots/map-intel-areas.png" />

**Intelligent Map — Affordability** — drag your budget and see the real % of currently listed rooms per area that fit (green/amber/red bars):

<img width="1440" alt="Intelligent Map Affordability" src="docs/screenshots/map-intel-affordability.png" />

**Roommate Matching** — find compatible flatmates by budget, area, lifestyle & gender preference:

<img width="1440" alt="Roommate Matching" src="docs/screenshots/roommates-matching.png" />

**Fraud Detection** — auto-scanned listings with risk scores & one-click re-scan from the landlord dashboard:

<img width="1440" alt="Fraud Detection Dashboard" src="docs/screenshots/fraud-detection.png" />

**Login / Register** — animated Dribbble-style auth dialog (live password strength meter in register mode):

<img width="1440" alt="Auth Login" src="docs/screenshots/auth-login.png" />

**Two-step verification (email OTP)** — password-first login pauses at a verification-code step; tokens are issued only after the code checks out:

<img width="1440" alt="OTP Verification" src="docs/screenshots/otp-verification.png" />

**KYC Verification** — upload identity documents from the landlord dashboard, review pending applications as admin, and see the decision trail (audit log):

<img width="1440" alt="KYC Upload" src="docs/screenshots/kyc-upload.png" />

<img width="1440" alt="KYC Admin Panel" src="docs/screenshots/kyc-admin-panel.png" />

**KYC Review SLA Stats** — the admin panel's queue-health strip (pending volume, average review time, 7-day decision trend) with red **breach badges** when the queue slips past 48h or trails last week:

<img width="1440" alt="KYC SLA Stats" src="docs/screenshots/kyc-sla.png" />

**KYC 30-day decision trend** — the History view's SVG chart: bars are decisions per day, the line is average review time, so the review team can see capacity at a glance:

<img width="1440" alt="KYC Trend Chart" src="docs/screenshots/kyc-trend-chart.png" />

**Phase 10 — Dashboard growth cards** — the referral invite card (copy link + WhatsApp/Facebook) and the browser push-notification toggle on the Dashboard overview:

<img width="1440" alt="Phase 10 Dashboard Growth" src="docs/screenshots/phase10-dashboard-growth.png" />

**Phase 10 — Landlord Insights** — per-listing views (7d/30d), wishlist saves, bookings and price vs area-average positioning:

<img width="1440" alt="Phase 10 Landlord Insights" src="docs/screenshots/phase10-insights.png" />

**Phase 10 — Saved Searches** — save the current search from the Rooms page and get alerted about new matching listings:

<img width="1440" alt="Phase 10 Saved Search" src="docs/screenshots/phase10-saved-search.png" />

**Phase 11 — AI Smart Search** — the ✨ AI Search toggle turns the search box into a natural-language query box: "দশ হাজার এর মধ্যে উত্তরা" (Bangla number *words* + Bangla area names) is understood as **budget ≤ ৳10,000 in Uttara** (see the "AI understood" chips under the bar) and ranked semantically — no keyword matching needed:

<img width="1440" alt="Phase 11 AI Smart Search" src="docs/screenshots/phase11-ai-search.png" />

**Phase 11++ — Rentora Copilot** — the floating conversational assistant: ask in Bangla, English or Banglish ("Uttara-তে ১০ হাজারের মধ্যে room") and it searches **live** listings — intent chips show what it understood, every listed room is a real retrieved row (no hallucination), and follow-ups keep context:

<img width="1440" alt="Rentora Copilot" src="docs/screenshots/copilot.png" />

**Phase 11++ — AI pricing suggestion v2** — landlord Insights row expanded: recommended price + range, demand score, confidence, time-to-rent and the explicit **Use price** action (nothing changes automatically):

<img width="1440" alt="AI Pricing Suggestion" src="docs/screenshots/pricing-suggestion.png" />

**Phase 7 v2 — Intelligent Map** — AI map search ("উত্তরায় ১২ হাজারের মধ্যে furnished room" → intent chips + real rooms + map flies to Uttara), metro commute scores, value-score pins, area intelligence with comparison, and the affordability budget view (screenshots in [🖼️ Screenshots](#-screenshots); architecture in [docs/INTELLIGENT_MAP.md](docs/INTELLIGENT_MAP.md)):

**Phase 7 v3 — Map UX polish** — zoom-aware area labels + boundary highlights in light mode (left) and dark mode (right):

<img width="1440" alt="Map UX Light" src="docs/screenshots/map-ux-light-default.png" />
<img width="1440" alt="Map UX Dark" src="docs/screenshots/map-ux-dark-state.png" />

**Phase 11++ — Cross-listing duplicate-image fraud** — admin Fraud Operations filtered to the duplicate-image detector, showing the HIGH-severity match with matched-listing chips:

<img width="1440" alt="Duplicate Image Fraud" src="docs/screenshots/duplicate-image-fraud.png" />

**Verified badge — dark theme** (the ✓ Verified pill stays legible in dark mode):

<img width="1440" alt="Verified Badge Dark" src="docs/screenshots/verified-badge-dark.png" />

**KYC on mobile** — the identity card + verified state on a phone-sized screen:

<img width="390" alt="KYC Mobile" src="docs/screenshots/kyc-mobile.png" />

**Phase 12 — Trust & Safety V2** — two-sided marketplace integrity:

**Tenant KYC** — the tenant-facing identity-verification card (Start Verification state) and the Reviewing state once a document is submitted:

<img width="1440" alt="Tenant KYC Upload" src="docs/screenshots/tenant-kyc-upload.png" />
<img width="1440" alt="Tenant KYC Pending" src="docs/screenshots/tenant-kyc-pending.png" />

**Verified tenant badge** — the ✓ Identity Verified mark next to an identity-verified tenant's name in the chat header (landlords never see the NID or document):

<img width="1440" alt="Verified Tenant Badge" src="docs/screenshots/verified-tenant-badge.png" />

**Report / block** — the conversation header ⋮ menu with Report user and Block user:

<img width="1440" alt="Report Block" src="docs/screenshots/report-block.png" />

**Chat safety feed** — the admin feed of chat-safety assessments (MEDIUM / HIGH / CRITICAL, metadata only):

<img width="1440" alt="Chat Safety Feed" src="docs/screenshots/chat-safety-feed.png" />

**Review moderation queue** — a held review (spam-ish contact info) with risk signals and approve/reject actions:

<img width="1440" alt="Moderation Reviews" src="docs/screenshots/moderation-reviews.png" />

**Photo moderation queue** — a flagged duplicate-image listing photo with its matched-listing evidence:

<img width="1440" alt="Moderation Photos" src="docs/screenshots/moderation-photos.png" />

**Dispute resolution (admin)** — the dispute list with evidence and the deposit decision (release / refund / partial):

<img width="1440" alt="Dispute Admin" src="docs/screenshots/dispute-admin.png" />

**Deposit protection (participant)** — a tenant's dispute on the approved booking that carries the paid security deposit:

<img width="1440" alt="Deposit Protection" src="docs/screenshots/deposit-protection.png" />

**Admin Trust & Safety Operations Center** — overview cards aggregating every queue (KYC, chat safety, reports, moderation, disputes):

<img width="1440" alt="Trust Center" src="docs/screenshots/trust-center.png" />

**Audit trail** — the read-only trail of every Phase 12 decision (who / when / what / why):

<img width="1440" alt="Audit Trail" src="docs/screenshots/audit-trail.png" />

**Phase 13 — Area SEO landing page** — `/rooms/dhanmondi` renders a crawlable per-area page with its own SEO title ("Rooms for rent in Dhanmondi, Dhaka"), meta description, area intro and the live room grid:

<img width="1440" alt="Phase 13 Area Page" src="docs/screenshots/phase13-area-page.png" />

**Phase 13 — Share on WhatsApp** — the room modal's share button opens a pre-filled WhatsApp message with the deterministic AI listing summary + deep link:

<img width="512" alt="Phase 13 WhatsApp Share" src="docs/screenshots/phase13-whatsapp-share.png" />

**Phase 13 — SMS phone sign-in** — the phone-first login box in the auth dialog (masked number, resend cooldown; the backend SMS endpoints are gateway-gated and answer `503` until enabled):

<img width="512" alt="Phase 13 SMS Login" src="docs/screenshots/phase13-sms-login.png" />

**Phase 14 — Photo intelligence** — the landlord dashboard's per-listing panel: analyzed caption, dominant-colour palette, evidence observations, suggested amenity tags (review-then-apply) and the AI draft title + description generated from the actual photos:

<img width="1216" alt="Phase 14 Vision Panel" src="docs/screenshots/phase14-vision-panel.png" />

**Phase 14 — AI image search** — upload any room photo (preview included) and Rentora finds listings that look like it:

<img width="448" alt="Phase 14 Image Search Dialog" src="docs/screenshots/phase14-image-search-dialog.png" />

**Phase 14 — Image search results** — look-alike listings ranked by perceptual similarity, each card carrying its match score badge with the reasons in the tooltip:

<img width="1440" alt="Phase 14 Image Search Results" src="docs/screenshots/phase14-image-search-results.png" />

**Phase 15 — Weekly market report (admin Analytics)** — area-level median rent, WoW movement and index for `Mirpur` (product analytics are first-party, the funnel is baked from events) — condensed rendering of the areas table in the **Analytics** tab of the Trust & Safety center:

<img width="1440" alt="Phase 15 Market Report" src="docs/screenshots/phase15-market-report.png" />

**Phase 15 — KYC OCR** (auto-extracted NID number/name/DOB with confidence), **AI review summary** (sentiment breakdown + topic tags on the room modal), **dynamic pricing v2** and **fraud rings** (coordinated accounts flagged via shared phone):

<img width="640" alt="Phase 15 KYC OCR" src="docs/screenshots/phase15-kyc-ocr.png" />
<img width="640" alt="Phase 15 Review AI Summary" src="docs/screenshots/phase15-review-ai-summary.png" />

**Phase 15 — Chat translation (EN⇄BN)** with honest quality flag, **support Copilot** (grounded FAQ answers, BN fallback), **voice TTS** on Copilot replies, and **price suggestion v2** (demand-momentum window):

<img width="640" alt="Phase 15 Chat Translate" src="docs/screenshots/phase15-chat-translate.png" />
<img width="640" alt="Phase 15 Copilot Support" src="docs/screenshots/phase15-copilot-support.png" />

**Phase 15 — Copilot voice (TTS)** on assistant replies and **fraud rings** surfaced in the admin Frauds panel:

<img width="640" alt="Phase 15 Copilot TTS" src="docs/screenshots/phase15-copilot-tts.png" />
<img width="640" alt="Phase 15 Fraud Rings" src="docs/screenshots/phase15-fraud-rings.png" />

**Phase 15 — Dynamic pricing v2** — demand-momentum-adjusted price windows with area-specific drivers, replacing static v1:

<img width="640" alt="Phase 15 Price V2" src="docs/screenshots/phase15-price-v2.png" />

**Phase 16 — Similar Rooms (embeddings runtime)** — the content-based carousel in every room modal: listings ranked by area, room type, price band and amenity overlap with match % and explainable reasons:

<img width="1440" alt="Phase 16 Similar Rooms" src="docs/screenshots/phase16-similar-rooms.png" />

**Phase 17 — Fraud graph admin** — the `GraphNode` changelist: entities (hosts/tenants/phone), labels, risk scores and detected communities after a rebuild:

<img width="1440" alt="Phase 17 Fraud Graph Admin" src="docs/screenshots/phase17-fraud-graph-admin.png" />

**Phase 18 — AI Intelligence Dashboard** — admin **AI** tab: per-feature/ provider/model health, cost, latency, error taxonomy, drift tri-state and a read-only A/B variant comparison over live telemetry:

<img width="1440" alt="Phase 18 AI Dashboard" src="docs/screenshots/phase18-ai-dashboard.png" />

**Phase 19.1 — Property Intelligence inspector (admin)** — the read-only per-room inspector: composite 0–100 score with weight/confidence breakdown, strengths + rule-based suggestions and staff-only provenance/market benchmarks:

<img width="1440" alt="Phase 19.1 Property Intelligence" src="docs/screenshots/phase19-1-property-intelligence.png" />

**Phase 19.2 — AI Rental Agent (tenant-facing grounded chat)** — Bengali-first agent inside the Copilot AI Tools: a real search turn ("মিরপুরে ২২০০০ টাকার মধ্যে একটা স্টুডিও রুম দেখাও") returns **grounded room cards** (Premium Studio · Cozy Studio), and the bookmark request sits in an amber **"await approval"** consent row the tenant reviews before the agent applies:

<img width="1440" alt="Phase 19.2 AI Rental Agent" src="docs/screenshots/phase19-2-rental-agent.png" />

**Home & Listing Pages:**

<img width="1920" height="2178" alt="RentRoom_BD" src="https://github.com/user-attachments/assets/8e7cd2b5-174e-4855-a8d6-beea394a12cc" />
<img width="1920" height="1433" alt="RentRoom_BD__1_" src="https://github.com/user-attachments/assets/e03dcd15-632b-4e2d-8659-de4bc2946f43" />
<img width="1920" height="927" alt="RentRoom_BD__3_" src="https://github.com/user-attachments/assets/6dc84e24-8d02-4cf5-a6a6-3ff926b21371" />
<img width="1920" height="927" alt="RentRoom_BD__2_" src="https://github.com/user-attachments/assets/6b958b77-127f-4424-8b62-76b6f6a09520" />

---

## 🔄 Team Workflow

**Branching**
- `main` is protected — never commit directly to it; all work ships on a branch.
- Branch naming: `feature/phase-<N>-<slug>` · `fix/<slug>` · `docs/<slug>` · `chore/<slug>` · `refactor/<slug>`.
- Branch off a freshly fetched upstream `main` (e.g. `git checkout -b feature/phase-19-3-listing-autopilot upstream/main`); keep branches short-lived — one phase per branch, merged within the day.
- Never force-push a shared branch.

**Pull requests**
- Every branch ships as a PR against `main` with a required title (`<type>(<scope>): <summary>`) and a description covering what/why, files touched, testing performed and screenshots for any UI change.
- CI must be **fully green** before merge — all gates: Frontend (Vitest + build + format + lint + coverage), Backend (Django tests + security/static audit), Secret scan (gitleaks), Browser E2E (Playwright), E2E (fraud + payments + KYC), API contract + schema drift, Frontend contract (schema → TS types), npm audit, Lighthouse performance gate.
- Squash-merge (or fast-forward) by the authorized account; never merge your own open PR; every merge carries an implicit one-click rollback plan.

**Local gates (pre-commit: husky + lint-staged)**
- Staged `.ts/.tsx/.mjs/.js` → Prettier + ESLint; staged `.py` → ruff; run `tsc --noEmit` and the CI format check locally before pushing so local == CI.
- Secret scanning runs alongside lint-staged — no commit ships credentials.
- Prettier (3.9.x) is pinned via the lockfile, so formatting is identical in local, CI and pre-commit.

**Environments**
- Local dev: SQLite + `manage.py runserver` (+ Redis via Docker when needed).
- CI: GitHub Actions on every PR and `main` — same tooling and constraints as local.
- Staging: PostgreSQL 16 + Redis + Celery with feature-flag review before release.
- Production: PostgreSQL 16 + Redis + Celery + Daphne/Channels + CDN media (Phase 8); secrets live in Actions secrets/environment variables only — never in the repository.
- Every service reports `/health/`, correlates via `X-Request-ID` and writes an audit log for state changes; releases follow the deploy window + rollback runbook.

**Release cadence**
- Phase-based delivery: one phase per day → branch → PR → green CI → merge → deploy; the changelog line comes from the PR title using Conventional Commit types (`feat` / `fix` / `docs` / `chore` / `refactor` / `style` / `test`).

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contributor guide, [CHANGELOG.md](CHANGELOG.md) for the release history, [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community norms and [SUPPORT.md](SUPPORT.md) for help channels.

---

## 👨‍💻 Developer

**Sadman Chowdhury Fahim**

- GitHub: [@SadManFahIm](https://github.com/SadManFahIm)

---

## 📄 License

This project is licensed under the MIT License.
