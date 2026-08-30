# Phase 18.3 — AI Evaluation Framework

**Date**: August 26, 2026  
**Status**: Shipped  
**Scope**: Evaluation metrics, golden datasets, evaluation runs, evaluator abstraction, model/prompt comparison, regression detection

---

## Overview

Phase 18.3 extends the AI Intelligence Layer from 18.2 (prompt registry + feature flags) with a complete evaluation framework:

1. **Evaluation Metrics** — configurable metric definitions with thresholds
2. **Golden Datasets** — versioned, publishable test datasets
3. **Evaluation Runs** — execute evaluations against datasets with pass/fail tracking
4. **Evaluator Abstraction** — 26 built-in evaluators (search, classification, fraud, LLM, general, prediction)
5. **Model/Prompt Comparison** — side-by-side run comparisons
6. **Regression Detection** — automatic threshold breach detection
7. **Async Task Execution** — Celery task for long-running evaluations

---

## Models

### `EvaluationMetric`

| Field | Type | Description |
|-------|------|-------------|
| `metric_key` | CharField (unique) | e.g. `f1`, `ndcg`, `precision_at_k` |
| `name` | CharField | Human-readable name |
| `description` | TextField | What this metric measures |
| `metric_type` | CharField | `deterministic`, `heuristic`, `llm_judge` |
| `category` | CharField | `search`, `classification`, `fraud`, `llm`, `general`, `prediction` |
| `formula` | TextField | Optional formula reference |
| `is_higher_better` | BooleanField | Direction of better scores |
| `default_threshold` | FloatField | Default threshold for regression checks |

### `EvaluationDataset`

| Field | Type | Description |
|-------|------|-------------|
| `dataset_key` | CharField | e.g. `searchrecision_test`, `fraud.detection_v2` |
| `version` | PositiveIntegerField | Auto-incrementing version |
| `name` | CharField | Human-readable name |
| `description` | TextField | What this dataset tests |
| `feature` | FK → AIFeatureRegistry | Optional feature association |
| `dataset_type` | CharField | `search`, `classification`, `fraud`, `llm`, `general` |
| `status` | CharField | `draft`, `published`, `archived` |
| `sample_count` | PositiveIntegerField | Auto-counted case count |
| `created_by` | CharField | Who created this version |

**Constraints**: Unique on (`dataset_key`, `version`)

### `EvaluationCase`

| Field | Type | Description |
|-------|------|-------------|
| `dataset` | FK → EvaluationDataset | Parent dataset |
| `case_id` | CharField | Stable identifier across versions |
| `input` | JSONField | Test input |
| `expected_output` | JSONField | Expected AI output |
| `expected_labels` | JSONField | Valid label set for classification |
| `metadata` | JSONField | Evaluation metadata |
| `evaluation_criteria` | JSONField | How to evaluate this case |

### `EvaluationThreshold`

| Field | Type | Description |
|-------|------|-------------|
| `feature` | FK → AIFeatureRegistry | Feature to monitor |
| `metric` | FK → EvaluationMetric | Metric to track |
| `threshold_min` | FloatField (nullable) | Minimum acceptable value |
| `threshold_max` | FloatField (nullable) | Maximum acceptable value |

**Constraints**: Unique on (`feature`, `metric`)

### `EvaluationRun`

| Field | Type | Description |
|-------|------|-------------|
| `run_key` | UUIDField (unique) | Unique run identifier |
| `feature` | FK → AIFeatureRegistry | Feature being evaluated |
| `dataset` | FK → EvaluationDataset | Dataset used |
| `prompt` | FK → AIPrompt (nullable) | Optional prompt being tested |
| `model_name` | CharField | Model variant name |
| `provider` | CharField | AI provider |
| `experiment_key` | CharField | Link to experiment system |
| `variant_key` | CharField | Experiment variant |
| `status` | CharField | `pending`, `running`, `completed`, `failed`, `cancelled` |
| `started_at` | DateTimeField | Run start time |
| `completed_at` | DateTimeField | Run completion time |
| `duration_ms` | PositiveIntegerField | Total duration |
| `total_cases` | PositiveIntegerField | Cases evaluated |
| `passed_cases` | PositiveIntegerField | Cases that passed |
| `score` | FloatField | Overall composite score |
| `metric_scores` | JSONField | Per-metric breakdown |
| `total_cost_usd` | DecimalField | Cost tracking |

### `EvaluationCaseResult`

| Field | Type | Description |
|-------|------|-------------|
| `run` | FK → EvaluationRun | Parent run |
| `case` | FK → EvaluationCase (nullable) | Source case |
| `input_data` | JSONField | Snapshot of input |
| `actual_output` | JSONField | AI's actual output |
| `expected_output` | JSONField | Expected output snapshot |
| `metric_results` | JSONField | Per-metric scores |
| `passed` | BooleanField | Whether this case passed |
| `score` | FloatField | Composite case score |
| `latency_ms` | PositiveIntegerField | Case evaluation time |
| `error_message` | TextField | Sanitized error if failed |
| `evaluator_version` | CharField | Evaluator version used |

---

## Evaluator Framework

### Built-in Evaluators (26 total)

**Search** (6):
- `search.precision_at_k` — Precision@K
- `search.recall_at_k` — Recall@K
- `search.ndcg` — Normalized Discounted Cumulative Gain
- `search.mrr` — Mean Reciprocal Rank
- `search.relevance_score` — Binary relevance

**Classification** (4):
- `classification.accuracy` — Accuracy
- `classification.precision` — Precision
- `classification.recall` — Recall
- `classification.f1` — F1 Score

**Fraud** (5):
- `fraud.precision` — Fraud precision
- `fraud.recall` — Fraud recall
- `fraud.f1` — Fraud F1
- `fraud.false_positive_rate` — False positive rate
- `fraud.false_negative_rate` — False negative rate

**LLM** (5):
- `llm.task_success` — Task completion check
- `llm.relevance` — Relevance scoring
- `llm.completeness` — Completeness check
- `llm.hallucination_rate` — Hallucination detection
- `llm.structured_output_validity` — JSON/schema validity

**General** (3):
- `general.exact_match` — Exact string match
- `general.contains` — Substring containment
- `general.length_ratio` — Output/input length ratio

**Prediction** (3):
- `prediction.mae` — Mean Absolute Error
- `prediction.rmse` — Root Mean Squared Error
- `prediction.r_squared` — R² Score

### Custom Evaluators

```python
from ai_intelligence.evaluators import register_evaluator

def my_evaluator(case_input, actual_output, expected_output, metadata):
    score = compute_score(case_input, actual_output, expected_output)
    return {"my_metric": score}

register_evaluator("custom.my_metric", my_evaluator, "Custom metric description")
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/ai/eval/metrics/` | List all metrics |
| GET | `/api/v1/ai/eval/datasets/` | List all datasets |
| POST | `/api/v1/ai/eval/datasets/` | Create new dataset |
| GET | `/api/v1/ai/eval/datasets/{id}/` | Get dataset detail |
| GET | `/api/v1/ai/eval/cases/` | List cases (filter by dataset) |
| GET | `/api/v1/ai/eval/thresholds/` | List thresholds |
| GET | `/api/v1/ai/eval/runs/` | List evaluation runs |
| GET | `/api/v1/ai/eval/runs/{id}/` | Get run detail with case results |
| POST | `/api/v1/ai/eval/runs/` | Create new evaluation run |
| POST | `/api/v1/ai/eval/runs/{id}/execute/` | Execute a run |
| POST | `/api/v1/ai/eval/runs/{id}/cancel/` | Cancel a running evaluation |
| GET | `/api/v1/ai/eval/case-results/` | List case results (filter by run) |
| POST | `/api/v1/ai/eval/compare/runs/` | Compare two runs |
| POST | `/api/v1/ai/eval/compare/models/` | Compare runs by model |
| POST | `/api/v1/ai/eval/compare/prompts/` | Compare runs by prompt |
| POST | `/api/v1/ai/eval/regression/check/` | Check run for regressions |
| GET | `/api/v1/ai/eval/baselines/` | Get latest baselines per feature |

---

## Celery Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `ai_intelligence.execute_evaluation_run` | On-demand | Execute an evaluation run |
| `ai_intelligence.cancel_stale_evaluation_runs` | Every 30 min | Cancel runs stuck >1 hour |

---

## Service Layer Functions

### Metrics
- `register_metric(metric_key, name, metric_type, category, ...)` — Register or update a metric

### Thresholds
- `set_threshold(feature_id, metric_key, threshold_min, threshold_max)` — Set evaluation threshold
- `get_thresholds(feature_id)` — Get all thresholds for a feature

### Datasets
- `create_dataset(dataset_key, name, description, feature_id, ...)` — Create dataset (version 1)
- `create_dataset_version(dataset_key, name, ...)` — Clone to new version
- `publish_dataset(dataset_key, version)` — Publish a draft dataset
- `archive_dataset(dataset_key, version)` — Archive a published dataset
- `add_cases(dataset_key, version, cases)` — Add cases to a dataset
- `get_dataset(dataset_key, version=None)` — Get dataset (latest if no version)

### Runs
- `create_evaluation_run(feature_id, dataset_key, ...)` — Create a pending run
- `execute_evaluation_run(run_id)` — Execute a run synchronously
- `cancel_evaluation_run(run_id)` — Cancel a running/pending run

### Comparison
- `compare_runs(run_a_id, run_b_id)` — Compare two specific runs
- `compare_models(feature_id, model_a, model_b, dataset_key)` — Compare model variants
- `compare_prompts(feature_id, prompt_a_key, prompt_b_key, dataset_key)` — Compare prompts

### Regression
- `check_regression(run_id)` — Check run against configured thresholds
- `get_latest_baselines(feature_id)` — Get baseline runs per feature

---

## Migration

- `0005_evaluationmetric_evaluationdataset_evaluationcase_*.py` — Creates all 6 evaluation models with indexes and constraints

---

## Test Coverage

- **107 ai_intelligence tests** (63 existing + 44 new Phase 18.3)
- **3 config.test_tasks tests** (task registration + beat schedule validation)
- **1356 total backend tests** (1 pre-existing failure in analytics, unrelated)

### New Test Classes
- `EvaluationMetricTests` (3 tests)
- `EvaluationThresholdTests` (6 tests)
- `EvaluationDatasetTests` (8 tests)
- `EvaluatorTests` (8 tests)
- `EvaluationRunTests` (5 tests)
- `ComparisonTests` (2 tests)
- `RegressionDetectionTests` (2 tests)
- `TaskTests` (2 tests)
- `EvaluationAPITests` (7 tests)
