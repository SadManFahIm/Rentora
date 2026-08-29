# Phase 18.4 — AI Intelligence Dashboard + Alerts

**Date**: August 29, 2026  
**Status**: Shipped  
**Scope**: Read-side AI operations dashboards (cached), configurable alert rules with anti-noise, admin alert lifecycle, Celery beat tasks, admin UI (Dashboard → AI tab)

---

## Overview

Phase 18.4 completes the AI Intelligence Layer from 18.1–18.3 with the two missing operational surfaces:

1. **AI Intelligence Dashboard** — cached admin dashboards over `AIExecutionLog` telemetry, `EvaluationRun` results, `ProviderHealth`, `AIPrompt` config, and Phase 17 `DriftMetric` data. 12 read-only endpoints under `/api/v1/ai/dashboard/`.
2. **AI Alerts** — `AIAlertRule` (metric + threshold + scope) and `AIAlert` (full lifecycle) models, a periodic Celery evaluation task, and a manual evaluation endpoint. Anti-noise engineered in: dedup, cooldown, consecutive breaches.
3. **Admin UI** — Dashboard → **AI** tab with 11 sub-views (Overview, Features, Models, Providers, Cost, Performance, Errors, Quality, Drift, Prompts, Alerts) and inline alert-rule management.

Everything is **ESTIMATED USD** (from `AIExecutionLog.estimated_cost_usd`) — never presented as billing.

---

## Models

### `AIAlertRule`

| Field | Type | Description |
|-------|------|-------------|
| `rule_key` | CharField (unique) | e.g. `copilot_error_rate` |
| `name` | CharField | Human-readable name |
| `description` | TextField | Optional notes |
| `alert_type` | CharField | `reliability`, `performance`, `quality`, `cost`, `drift`, `availability` |
| `metric` | CharField | `error_rate`, `timeout_rate`, `fallback_rate`, `success_rate`, `avg_latency`, `p95_latency`, `daily_cost`, `cost_per_execution`, `evaluation_score`, `drift_breach` |
| `operator` | CharField | `gt`, `gte`, `lt`, `lte` |
| `threshold_value` | FloatField | Threshold the metric is compared against |
| `feature` | FK → AIFeatureRegistry (nullable) | Scope (null = all features) |
| `provider` / `model_name` | CharField | Optional scope filters |
| `duration_minutes` | PositiveIntegerField | Metric look-back window (default 5) |
| `consecutive_checks` | PositiveIntegerField | Trigger only after N consecutive breaches |
| `cooldown_minutes` | PositiveIntegerField | Min minutes between alerts for the same scope |
| `severity` | CharField | `info`, `warning`, `critical` |
| `is_enabled` / `notify_admins` | BooleanField | Gate + in-app notification toggle |
| `breach_count`, `last_metric_value`, `last_checked_at` | State | Written by the evaluation task |
| `created_by` | FK → User | Rule author |

### `AIAlert`

| Field | Type | Description |
|-------|------|-------------|
| `alert_key` | UUID (unique) | Used in deep links (`/dashboard?tab=ai&view=alerts&alert=<key>`) |
| `rule`, `alert_type`, `severity` | FKs / choices | Snapshot of the rule that fired |
| `status` | CharField | `triggered` → `acknowledged` → `resolved`, or `suppressed` |
| `title`, `message` | Text | Human-readable alert content |
| `metric_name`, `metric_value`, `threshold_value` | Metrics | The observed breach |
| `feature`, `provider`, `model_name` | Scope | Where it fired |
| `dedup_key` | CharField (db_index) | sha256(rule_key + "feature::provider::model") — folds repeated breaches into one open alert |
| `breach_count` | PositiveIntegerField | Current streak at trigger |
| `acknowledged_by` / `resolved_by` | FK → User | Lifecycle actors |
| `resolution_note` | TextField | Why it was resolved/suppressed |
| `triggered_at`, `updated_at` | DateTime | Timing |

**Indexes**: `(alert_type, triggered_at)`, `(status, triggered_at)`, `(severity, status)`.

---

## Alerts engine (`ai_intelligence/alerts.py`)

- **`compute_metric_value(rule)`** — computes the current metric for the rule's scope + `duration_minutes` window. Rates are `count / total * 100`; latency uses capped sample percentiles (nearest-rank, 20k sample cap); `daily_cost` intentionally uses a **1440-minute** look-back so the "daily" label stays honest at any task cadence; `evaluation_score` reads the latest completed `EvaluationRun.score`; `drift_breach` counts `DriftMetric.threshold_breached` in the scope. Returns `None` when there is no data (never triggers).
- **`_is_breach(rule, value)`** — operator comparison.
- **Anti-noise** —
  - *Dedup*: an open (triggered/acknowledged) alert for the same `dedup_key` absorbs continued breaches (breach_count/metric_value updated, nothing new created).
  - *Cooldown*: no re-trigger within `cooldown_minutes` of a recent alert.
  - *Consecutive*: `breach_count` accumulates and resets on recovery; only reaches trigger once `>= consecutive_checks`.
- **`evaluate_rule` / `evaluate_all_rules`** — single-rule or batch evaluation. `evaluate_all_rules` returns `{evaluated, results, counts}`.
- **Lifecycle** — `acknowledge_alert`, `resolve_alert`, `suppress_alert` (ValueError on invalid transitions). Every transition is audited via `log_action` (`ai_intelligence.alert_triggered/acknowledged/resolved/suppressed`).
- **Notifications** — `create_notification(user, notification_type="ai_alert", …)` to every active staff-or-admin user (`Q(is_staff=True) | Q(role="admin")`), deep-linking into the dashboard.

### Beat tasks (`ai_intelligence/tasks.py` + settings)

| Task | Beat schedule | Purpose |
|------|---------------|---------|
| `ai_intelligence.evaluate_alert_rules` | every 300 s | Evaluate all enabled rules, notify + audit on trigger |
| `ai_intelligence.warm_dashboard_cache` | every 1800 s | Pre-compute dashboard aggregates into cache |

Setting: `AI_DASHBOARD_CACHE_TTL_SECONDS` (default 300).

---

## Dashboard service (`ai_intelligence/dashboard.py`)

All read-side functions are pure aggregate queries with no writes. Results are cached under `ai:dashboard:*` for the TTL and invalidated with `invalidate_dashboard_cache()` when any evaluation completes.

| Function | Returns |
|----------|---------|
| `get_ai_summary(days, feature_id, provider, model)` | KPIs, error/success/fallback rates, latency percentiles, cost/tokens, active features/models, drift status, open alerts, daily trend |
| `get_feature_health_list(days)` / `get_feature_health_detail(feature_id, days)` | Per-feature telemetry + latest evaluation + active prompt; drill-down with quality/regression, cost breakdown, drift context |
| `get_model_health(days)` / `compare_model_versions(provider, model, a, b)` | Per-(provider, model) health + latest eval; read-only A/B of two model variants (never switches production) |
| `get_provider_health(days)` | Telemetry + latest hourly `ProviderHealth` window (availability status) |
| `get_cost_dashboard(days)` | ESTIMATED USD totals, per-feature/provider/model breakdown, daily trend, anomalies (cost increase vs previous window ≥ 20%, single-feature concentration > 60%) |
| `get_performance_dashboard(days)` | Latency percentiles, daily avg trend, per-feature/provider/model breakdown, abnormal-latency detection (>20% vs previous window) |
| `get_error_dashboard(days, feature_id)` | Error/timeout/fallback rates, failure-type + status breakdowns, top fallback reasons (sanitized) |
| `get_quality_dashboard(days)` | Latest completed evaluation per feature with per-category metrics, evaluator taxonomy, `_metric_catalog()` from `EvaluationMetric` |
| `get_drift_status(model_name)` | Latest `DriftMetric` per (model, metric) with derived healthy/warning/critical/unknown (warning = within 10% of an active threshold boundary) — reuses Phase 17 data, no second drift engine |
| `get_prompt_health(days)` | Active/previous version, feature, model, latest evaluation per `AIPrompt` |

### API (`/api/v1/ai/`, admin-only — staff or role=admin)

`dashboard/summary/`, `dashboard/features/`, `dashboard/features/<feature_id>/`, `dashboard/models/`, `dashboard/models/compare/`, `dashboard/providers/`, `dashboard/cost/`, `dashboard/performance/`, `dashboard/errors/`, `dashboard/quality/`, `dashboard/drift/`, `dashboard/prompts/`; `alerts/rules/` (list/create), `alerts/rules/<id>/` (get/update/delete), `alerts/` (list + severity/status/type/feature filters), `alerts/<id>/`, `alerts/<id>/acknowledge/`, `alerts/<id>/resolve/`, `alerts/<id>/suppress/`, `alerts/evaluate/`.

---

## Admin UI (frontend)

New files:

- `services/aiIntelligenceService.ts` — typed client for all 12 dashboard + 8 alert endpoints (snake→camel mappers, `AiSummary`, `AiAlertRule`, `AiAlert`, …).
- `hooks/useAiIntelligence.ts` — react-query hooks (`useAiSummary`, …, `useAiAlerts`, `useCreateAiAlertRule`, `useAlertLifecycle`, `useEvaluateAiAlerts`).
- `components/AdminAiPanel/AdminAiPanel.tsx` — 11 sub-views including hand-rolled SVG trend charts (no chart lib), model A/B comparator, drift table, alert cards with acknowledge/resolve/suppress, and a rule editor modal (scope, threshold, operator, anti-noise, severity). Deep-link aware: `/dashboard?tab=ai&view=alerts&alert=<key>` highlights the alert that fired a notification.

`Dashboard.tsx` registers the admin-only **AI** tab (`isAdmin`, mirrors the backend RBAC).

---

## Engineering

- 55 new backend tests (1411 total BE suite, all green):
  - `AIAlertRuleModelTests`, `AlertMetricComputationTests`, `AlertEvaluationTests`, `AlertLifecycleTests` — engine
  - `DashboardServiceTests` — every aggregate function
  - `DashboardAPITests`, `AlertAPITests` — RBAC, CRUD, filters, lifecycle, evaluate
- 2 new models, 2 migrations (`ai_intelligence` 0006 + 0007, `notifications` 0014 for the `ai_alert` notification type).
- `config/test_tasks.py` updated for the exact task + beat sets.
- Frontend: TypeScript strict clean, ESLint clean, production build green.
- ruff-clean (verified pre-commit).

Costs are always displayed as **ESTIMATED USD** and the control-plane explicitly notes *production switch is never automated* — the model comparator is read-only by design.