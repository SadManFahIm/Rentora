# Phase 18.2 — Prompt Registry & Feature Integration

**Date**: August 25, 2026  
**Status**: Shipped  
**Scope**: Prompt/version management, feature-flag integration, AI feature seeding, expanded admin API

---

## Overview

Phase 18.2 extends the AI Intelligence Layer from 18.1 (provider registry + telemetry) with:

1. **Prompt Registry** — versioned prompt/template management with activate/deactivate/rollback
2. **Feature Flag Integration** — `is_feature_available()` checks both AI registry AND Django feature flags
3. **AI Feature Seeding** — `register_ai_features` management command seeds 30 real features from codebase audit
4. **Expanded Admin API** — 18 total endpoints (3 feature, 7 prompt, 2 log, 3 health, 3 version management)

---

## Models

### `AIPrompt`

| Field | Type | Description |
|-------|------|-------------|
| `prompt_key` | CharField (unique) | e.g. `ai.copilot.reply`, `ai.chat_safety.classify` |
| `name` | CharField | Human-readable name |
| `description` | TextField | What this prompt is for |
| `category` | CharField | `copilot`, `classification`, `nlp`, `pricing`, `vision`, `embedding`, etc. |
| `owner` | CharField | Team/developer who owns this prompt |
| `is_active` | BooleanField | Whether the prompt is live |
| `active_version` | FK→AIPromptVersion | The currently deployed version |
| `latest_version` | FK→AIPromptVersion | The most recently created version |
| `settings_key` | CharField | Django settings key for this feature |
| `metadata` | JSONField | Arbitrary config (model overrides, temperature, etc.) |

### `AIPromptVersion`

| Field | Type | Description |
|-------|------|-------------|
| `prompt` | FK→AIPrompt | Parent prompt |
| `version` | PositiveIntegerField | Auto-incrementing per prompt |
| `template` | TextField | The prompt template content (supports `{{variable}}` syntax) |
| `variables` | JSONField | Declared variable names with defaults |
| `model_overrides` | JSONField | Per-version model config (provider, model, temperature, etc.) |
| `changelog` | TextField | What changed in this version |
| `created_by` | FK→User | Who created this version |
| `created_at` | DateTimeField | Auto-set on creation (immutable) |
| `is_active` | BooleanField | Whether this version is the active one |

**Constraints**:
- `UniqueConstraint("prompt", "version")` — no duplicate versions per prompt
- Templates are immutable after creation (view blocks PUT/PATCH on `template` field)
- One active version per prompt — activating a new version deactivates the previous

### Extended `AIFeatureRegistry` (from 18.1)

New fields added in 18.2:
- `status` — `active` | `deprecated` | `disabled`
- `owner` — Team/developer responsible
- `default_model` — e.g. `gpt-4o`, `claude-3-sonnet`
- `fallback_strategy` — `none` | `fallback_provider` | `cached_response` | `rule_based`
- `feature_flag_key` — Links to a Django `FeatureFlag`

### Extended `AIExecutionLog` (from 18.1)

New fields added in 18.2:
- `prompt_key` — Which prompt was used (nullable, for backward compat)
- `prompt_version` — Which version was used (nullable)

---

## Services

### Prompt CRUD
- `create_prompt(prompt_key, name, category, ...)` — Creates prompt + optional first version
- `create_prompt_version(prompt, template, variables, ...)` — Adds a new version

### Prompt Versioning
- `activate_prompt_version(prompt, version)` — Activates a version, deactivates the previous
- `deactivate_prompt_version(prompt)` — Deactivates the current active version
- `rollback_prompt(prompt)` — Rolls back to the previous version

### Prompt Rendering
- `get_prompt_template(prompt_key)` — Returns active version template + variables
- `render_prompt(prompt_key, **kwargs)` — Fills variables into the template
- `validate_prompt_variables(prompt_key, variables)` — Checks for missing/unused variables

### Feature Flag Integration
- `is_feature_available(feature_id, user)` — Checks:
  1. `AIFeatureRegistry.is_enabled` (registry toggle)
  2. Linked `FeatureFlag.is_enabled()` (if `feature_flag_key` is set)
- Both must be True (or flag key not set) for the feature to be available

### Template Safety
- `_validate_template_safety(template)` — Rejects templates containing `API_KEY`, `SECRET`, `PASSWORD`, `TOKEN`, `PRIVATE_KEY`, `AWS_`, `OPENAI_API`, `ANTHROPIC_API`
- Enforced on both `AIPrompt` creation and `AIPromptVersion` creation

---

## API Endpoints

All under `api/v1/ai/` (staff-only unless noted):

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `features/` | List all AI features |
| GET | `features/<id>/` | Feature detail |
| PUT/PATCH | `features/<id>/update/` | Update feature config |
| POST | `prompts/` | Create prompt + first version |
| GET | `prompts/` | List all prompts |
| GET | `prompts/<key>/` | Prompt detail with version history |
| PUT/PATCH | `prompts/<key>/` | Update prompt metadata |
| POST | `prompts/<key>/versions/` | Create new version |
| GET | `prompts/<key>/versions/` | List versions |
| GET | `prompts/<key>/versions/<v>/` | Version detail |
| POST | `prompts/<key>/versions/<v>/activate/` | Activate a version |
| POST | `prompts/<key>/deactivate/` | Deactivate current version |
| POST | `prompts/<key>/rollback/` | Rollback to previous version |
| GET | `prompts/<key>/compare/?from=<v>&to=<v>` | Compare two versions |
| GET | `logs/` | List execution logs |
| GET | `logs/<uuid>/` | Log detail |
| GET | `health/` | Provider health list |
| GET | `health/stats/` | Provider stats (success rate, latency, cost) |
| POST | `health/update/` | Manually trigger health aggregation |

---

## Management Command

```bash
python manage.py register_ai_features
```

Seeds 30 AI features from a codebase audit. Idempotent — creates new, updates existing. Covers:

| Category | Features |
|----------|----------|
| NLP | `copilot.reply`, `chat_safety.classify`, `translation`, `voice_search` |
| Recommendation | `recommendations.rooms`, `recommendations.roommates`, `ai_search.semantic` |
| Pricing | `pricing.suggestion`, `pricing.forecast`, `pricing.negotiation` |
| Vision | `vision.photo_analysis`, `vision.image_search`, `vision.listing_draft` |
| Fraud | `fraud.listing_scan`, `fraud.review_detector`, `fraud.ring_detection` |
| KYC | `kyc.liveness`, `kyc.face_match`, `kyc.ocr` |
| Embedding | `embedding.neural`, `embedding.similarity` |
| Matching | `roommate.matching` |
| Agreements | `agreement.checker` |
| Translation | `chat.translate` |
| Analytics | `analytics.demand_forecast`, `analytics.price_index` |
| Recommendation v2 | `rental_advisor`, `property_comparison` |

---

## Celery Tasks (from 18.1, unchanged)

- `ai_intelligence.update_provider_health` — Hourly aggregation of execution logs into `ProviderHealth`
- `ai_intelligence.purge_old_execution_logs` — Daily cleanup of logs older than `AI_EXECUTION_LOG_RETENTION_DAYS`

---

## Engineering

- **63 tests** in `ai_intelligence/tests.py` covering:
  - Model creation + string representations
  - Prompt CRUD, versioning, rollback, rendering, variable validation
  - Template safety (forbidden patterns)
  - Feature flag integration
  - API endpoints (CRUD, version management, authorization)
  - Management command
  - Telemetry integration
- **4 migrations**: 0001 (initial), 0002 (execution_id unique), 0003 (drop redundant index), 0004 (Phase 18.2 models)
- **Lint clean** (ruff)
- **1312 backend tests passing** (was 1270)
