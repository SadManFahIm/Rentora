# Phase 18 — AI Evaluation + Intelligence Foundation: Architecture Audit

**Date**: August 24, 2026  
**Status**: Complete  
**Scope**: Comprehensive audit of existing AI infrastructure, telemetry, provider abstractions, and gaps

---

## Executive Summary

Rentora has **significant existing AI infrastructure** across multiple phases (13–17) that can be extended rather than rebuilt. The system currently lacks:

1. **Centralized telemetry** — No per-request logging of latency, tokens, cost, or success/failure rates
2. **Prompt management** — No versioning, A/B testing, or lifecycle management for prompts
3. **Evaluation framework** — No systematic way to measure AI output quality (accuracy, relevance, hallucination rates)
4. **Cost tracking** — No per-feature or per-model token usage or cost attribution
5. **Quality monitoring** — No real-time dashboards for AI performance degradation

**Recommendation**: Build Phase 18 as an **intelligence layer** that wraps existing infrastructure, not a replacement.

---

## 1. Current AI Provider Infrastructure

### 1.1 Provider Abstraction (`fraud/services/provider_base.py`)

**Existing Classes**:
- `BaseProvider(ABC)` — Abstract base with `name`, `timeout`, `max_retries`
- `ProviderResult` — Standardized result: `success`, `data`, `provider`, `latency_ms`, `error`, `error_code`, `cached`
- `ProviderFailure` — Failure record: `provider`, `failure_type`, `error`, `attempt`, `timestamp`
- `FailureType` — Enum: `TIMEOUT`, `AUTH_ERROR`, `RATE_LIMIT`, `INVALID_RESPONSE`, `NETWORK_ERROR`, `PROVIDER_ERROR`
- `Registry` — Singleton pattern with `register()`, `get()`, `list_providers()`, `record_failure()`, `is_healthy()`, `get_provider_status()`

**Current Usage** (2 of 25+ features):
- `fraud/services/kyc_providers/liveness.py` — Liveness detection
- `fraud/services/kyc_providers/face_match.py` — Face matching

**Gap**: 90% of AI features (copilot, chat safety, recommendations, pricing, embeddings) do NOT use this abstraction.

### 1.2 Provider Configuration (Django Settings)

**Existing Provider Keys** (from `config/settings/base.py`):
```python
# Fraud/KYC (Phase 13-14)
KYC_PROVIDER, KYC_OCR_PROVIDER, KYC_LIVENESS_PROVIDER, KYC_FACE_MATCH_PROVIDER
VISION_PROVIDER, SMS_PROVIDER, INSURANCE_PROVIDER, CREDIT_PROVIDER

# Chat/AI (Phase 15-16)
CHAT_SAFETY_ML_ENABLED, CHAT_TRANSLATE_PROVIDER, CHAT_TRANSLATE_GATEWAY_URL
CHAT_TRANSLATE_API_KEY, COPILOT_ENABLED

# Embeddings (Phase 16)
EMBEDDING_PROVIDER (lite/auto/neural/hosted), SEMANTIC_EMBEDDING_MODE
VECTOR_SEARCH_ENABLED, EMBEDDING_INDEX_ON_SAVE
```

**Gap**: No unified provider registry with health checks, fallback chains, or cost tracking.

---

## 2. Database Models (AI-Related)

### 2.1 Fraud App Models

**`FraudSignal`** (25+ fields):
- `signal_type`: scam, fake_listing, suspicious_booking, phishing, kyc_fraud, photo_geo_mismatch
- `confidence` (0-100), `severity` (low/medium/high/critical)
- `metadata` (JSON) — stores raw provider responses, risk_scores, geo_tags
- **Telemetry available**: `confidence` + `created_at` = time-series data

**`ScanResult`** (orchestrator result):
- `scanner_version`, `duration_ms`, `signals_found`, `scan_type`
- **Telemetry available**: `duration_ms` = latency metric

**`ScanFinding`** (per-rule results):
- `rule_id`, `rule_version`, `matched`, `evidence` (JSON)
- **Telemetry available**: `rule_id` = per-feature tracking

**`PhotoVerification`** (vision provider results):
- `provider`, `provider_reference`, `original_image_hash`, `processed_image_hash`
- `landmarks_detected` (JSON), `risk_flags` (JSON)
- `review_status`, `reviewed_by`, `reviewed_at`
- **Gap**: No `latency_ms`, `cost`, `tokens_used` fields

**`KYCRecord`** (KYC pipeline state):
- `ocr_provider`, `liveness_provider`, `face_match_provider`
- `ocr_confidence`, `liveness_score`, `face_match_score`
- `ocr_raw_response`, `liveness_raw_response`, `face_match_raw_response` (JSON)
- **Gap**: Raw responses stored but not parsed for telemetry

### 2.2 ML Models App

**`ModelVersion`** (Phase 17):
- `name`, `version`, `status` (active/deprecated/experimental)
- `training_date`, `metrics` (JSON), `artifacts_path`
- **Gap**: No `provider`, `cost_per_inference`, `max_tokens` fields

**`DriftMetric`** (Phase 17):
- `model_version` (FK), `metric_name`, `value`, `baseline_value`
- `threshold_min/max`, `threshold_breached`
- `window_start/end`, `sample_count` (always 0!)
- **Gap**: `sample_count` never populated; no per-request logging

**`RetrainRequest`** (Phase 17):
- `model_version` (FK), `reason`, `status` (pending/running/completed/failed/cancelled)
- `triggered_by` (FK User), `notes`, `created_at`, `completed_at`
- **Gap**: Status never auto-transitions; no task consumes it

### 2.3 Analytics App

**`Event`** (privacy-bounded):
- `user` (FK, nullable), `event`, `category`, `properties` (JSON, max 64 keys × 256 chars)
- `session_id`, `path`, `created_at`
- **Existing usage**: Product funnel (page_view → room_view → chat_started → booking → payment)
- **Gap**: No AI-feature events (copilot queries, semantic-search clicks, recommendation impressions)

### 2.4 Embeddings App

**`Embedding`** (pgvector):
- `entity_type`, `entity_id`, `model`, `dimensions`
- `vector` (VectorField 384d), `content_hash`, `metadata` (JSON)
- **Gap**: No `generation_time_ms`, `token_count`, `cost` fields

---

## 3. Telemetry & Monitoring Gaps

### 3.1 What EXISTS

| System | Location | What It Tracks |
|--------|----------|----------------|
| FraudSignal confidence | fraud/models.py | Confidence scores over time |
| ScanResult duration | fraud/models.py | Scan latency per room |
| DriftMetric | ml_models/models.py | Aggregate model health (accuracy, precision) |
| Analytics Event | analytics/models.py | Product funnel steps |
| Provider health | fraud/services/provider_base.py | Failure counts, last failure time |

### 3.2 What's MISSING (Phase 18 Scope)

| Gap | Impact | Priority |
|-----|--------|----------|
| **No per-request telemetry** | Cannot measure p50/p95 latency, success rates | CRITICAL |
| **No token/cost tracking** | Cannot attribute costs to features or users | CRITICAL |
| **No prompt management** | Cannot A/B test prompts, track versions | HIGH |
| **No evaluation framework** | Cannot measure output quality (accuracy, relevance) | HIGH |
| **No quality monitoring** | Cannot detect hallucinations, bias, degradation | HIGH |
| **No admin dashboard** | No visibility into AI system health | MEDIUM |
| **RetrainRequest never consumed** | Drift alerts ignored | MEDIUM |
| **sample_count always 0** | Drift metrics lack statistical significance | MEDIUM |

---

## 4. Existing AI Features (25+ Systems)

### 4.1 Fully AI-Powered (Need Telemetry)

| Feature | App | Provider | Current Telemetry |
|---------|-----|----------|-------------------|
| Copilot | copilot/ | Deterministic (no LLM) | None |
| Chat Safety ML | chat/ | ML model (local) | None |
| Chat Translation | chat/ | External API | None |
| Recommendations | recommendations/ | ML (collaborative filtering) | None |
| AI Pricing | pricing/ | ML (regression) | None |
| Semantic Search | embeddings/ | sentence-transformers/hosted/lite | None |
| Photo Verification | fraud/ | Vision API | None |
| KYC Liveness | fraud/ | Provider (base_provider) | Failure tracking only |
| Face Match | fraud/ | Provider (base_provider) | Failure tracking only |

### 4.2 Rule-Based (Not AI, No Telemetry Needed)

| Feature | App | Notes |
|---------|-----|-------|
| Scam Network Graph | fraud/ | NetworkX algorithms |
| Photo-Geo Mismatch | fraud/ | Geocoding + haversine |
| Fake Review Detection | fraud/ | Statistical heuristics |
| Model Drift Monitor | fraud/ | Aggregate metrics |

---

## 5. Architectural Recommendations

### 5.1 Core Intelligence Layer (Phase 18 Build)

```
┌─────────────────────────────────────────────────────────┐
│                    INTELLIGENCE LAYER                    │
├─────────────────────────────────────────────────────────┤
│  Provider Registry  │  Prompt Manager  │  Eval Framework │
│  (extends base_     │  (versioning,    │  (quality       │
│   provider.py)      │   A/B testing)   │   metrics)     │
├─────────────────────────────────────────────────────────┤
│  Telemetry Logger   │  Cost Tracker    │  Quality Monitor│
│  (per-request logs, │  (token counts,  │  (hallucination │
│   latency, errors)  │   cost attribution│  detection)   │
├─────────────────────────────────────────────────────────┤
│              Admin Dashboard (read-only)                │
│  • Real-time AI health  • Cost breakdown  • Quality trends │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                 EXISTING AI FEATURES                    │
│  copilot │ chat │ recommendations │ pricing │ fraud │ embeddings │
└─────────────────────────────────────────────────────────┘
```

### 5.2 Database Additions (Minimal)

**New Models**:
1. `AILog` — Per-request telemetry (provider, latency_ms, tokens, cost, success, feature, user)
2. `PromptVersion` — Prompt template versioning (name, version, template, variables, is_active)
3. `EvaluationRun` — Quality evaluations (feature, prompt_version, input, expected, actual, score)
4. `CostBudget` — Per-feature/per-user budget limits (feature, user, limit, period, current_usage)

**Existing Model Changes**:
- `DriftMetric.sample_count` — Populate with actual sample size
- `RetrainRequest` — Add auto-consumer task
- `PhotoVerification` — Add `latency_ms`, `cost` fields
- `Embedding` — Add `generation_time_ms`, `token_count`

### 5.3 Implementation Phases

**Phase 18.1**: Provider Registry + Telemetry Logger (Week 1)
- Extend `base_provider.py` with telemetry hooks
- Create `AILog` model + migration
- Add telemetry middleware to all AI features

**Phase 18.2**: Cost Tracker + Prompt Manager (Week 2)
- Token counting for LLM providers
- Cost attribution per feature/user
- `PromptVersion` model + admin

**Phase 18.3**: Evaluation Framework + Quality Monitor (Week 3)
- `EvaluationRun` model
- Hallucination detection heuristics
- Quality scoring pipeline

**Phase 18.4**: Admin Dashboard + Integration (Week 4)
- Django admin custom views
- Real-time health dashboard
- Alerting for quality degradation

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Performance overhead from logging | Async Celery tasks for non-critical logs |
| Storage bloat from per-request logs | Partitioning by month, auto-purge after 90 days |
| Provider API changes break telemetry | Versioned parsers, fallback to raw storage |
| Cost explosion from evaluation runs | Budget limits, sampling-based evaluation |
| Feature creep | Strict scope: wrap existing features, don't add new ones |

---

## 7. Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| AI request visibility | 100% of AI features logged | AILog coverage report |
| Latency tracking | p50 < 200ms, p95 < 1s | AILog aggregation |
| Cost attribution | 100% of token costs attributed | CostTracker daily report |
| Quality monitoring | Hallucination rate < 5% | EvaluationRun scoring |
| Admin visibility | Dashboard with 24h refresh | Admin view metrics |

---

## 8. Conclusion

Rentora has **strong foundations** (provider abstraction, drift monitoring, analytics) that can be extended. Phase 18 should:

1. **NOT rebuild** what exists (provider registry, drift metrics)
2. **ADD telemetry layer** on top of existing features
3. **ADD evaluation framework** for quality measurement
4. **ADD cost tracking** for financial visibility
5. **ADD admin dashboard** for operational visibility

**Estimated Effort**: 4 weeks (1 developer)  
**Risk Level**: Medium (extends existing patterns, low refactoring)  
**Impact**: High (enables data-driven AI optimization)

---

*Audit completed by: AI Assistant*  
*Reviewed by: Sadman Chowdhury Fahim*  
*Status: Pending approval before implementation*