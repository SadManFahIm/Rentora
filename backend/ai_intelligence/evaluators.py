"""AI Intelligence Layer — Phase 18.3 evaluator abstraction + built-in evaluators.

Provides a reusable evaluator architecture:

    Evaluation → Evaluator → Metric → Result

Evaluator types:
- ``deterministic``: exact match, regex, rule-based scoring
- ``heuristic``: scoring heuristics (e.g. keyword overlap, length ratios)
- ``llm_judge``: uses an LLM to evaluate output quality (clearly labeled)
- ``human``: placeholder for manual evaluation (not auto-scored)

Built-in evaluators cover:
- Search: precision@K, recall@K, NDCG, MRR, relevance score
- Classification: accuracy, precision, recall, F1
- Fraud: precision, recall, false-positive rate, false-negative rate
- LLM: task success, groundedness, relevance, hallucination rate
- General: exact match, contains, length ratio

Do NOT hard-code evaluation logic into individual AI features.
Each feature defines its appropriate evaluator via the registry.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluator Registry
# ---------------------------------------------------------------------------

_EVALUATORS: dict[str, callable] = {}


def register_evaluator(category: str, func: callable) -> None:
    """Register an evaluator function for a feature category.

    The function signature must be:
        func(case_input, actual_output, expected_output, case_metadata) -> dict
    returning a dict of metric_key -> value.
    """
    _EVALUATORS[category] = func


def get_evaluator(category: str) -> callable | None:
    """Return the evaluator function for a category, or None."""
    return _EVALUATORS.get(category)


def evaluate_case(
    category: str,
    case_input: Any,
    actual_output: Any,
    expected_output: Any | None = None,
    case_metadata: dict | None = None,
) -> dict[str, float]:
    """Run the appropriate evaluator for a case and return metric scores.

    Returns a dict of metric_key -> value. Returns empty dict if no
    evaluator is registered for the category.
    """
    evaluator = get_evaluator(category)
    if evaluator is None:
        return {}
    try:
        return evaluator(case_input, actual_output, expected_output, case_metadata or {})
    except Exception:
        logger.exception("Evaluator failed for category=%s", category)
        return {}


# ---------------------------------------------------------------------------
# Search Evaluators
# ---------------------------------------------------------------------------


def _precision_at_k(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Precision@K: fraction of returned items that are relevant."""
    k = metadata.get("k", 5)
    if not isinstance(actual_output, list) or not isinstance(expected_output, list):
        return {"precision_at_k": 0.0}
    relevant_set = set(str(r) for r in expected_output)
    retrieved = [str(r) for r in actual_output[:k]]
    if not retrieved:
        return {"precision_at_k": 0.0}
    hits = sum(1 for r in retrieved if r in relevant_set)
    return {"precision_at_k": hits / len(retrieved)}


def _recall_at_k(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Recall@K: fraction of relevant items that are returned."""
    k = metadata.get("k", 5)
    if not isinstance(actual_output, list) or not isinstance(expected_output, list):
        return {"recall_at_k": 0.0}
    relevant_set = set(str(r) for r in expected_output)
    if not relevant_set:
        return {"recall_at_k": 1.0}
    retrieved = [str(r) for r in actual_output[:k]]
    hits = sum(1 for r in retrieved if r in relevant_set)
    return {"recall_at_k": hits / len(relevant_set)}


def _ndcg(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Normalized Discounted Cumulative Gain."""
    k = metadata.get("k", 10)
    if not isinstance(actual_output, list) or not isinstance(expected_output, list):
        return {"ndcg": 0.0}
    relevant_set = set(str(r) for r in expected_output)
    if not relevant_set:
        return {"ndcg": 1.0}

    def dcg(retrieved: list[str]) -> float:
        return sum(
            (1.0 if str(r) in relevant_set else 0.0) / math.log2(i + 2)
            for i, r in enumerate(retrieved[:k])
        )

    actual_dcg = dcg([str(r) for r in actual_output])
    ideal_dcg = dcg(list(relevant_set)[:k])
    if ideal_dcg == 0:
        return {"ndcg": 0.0}
    return {"ndcg": actual_dcg / ideal_dcg}


def _mrr(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Mean Reciprocal Rank: 1/rank of first relevant result."""
    if not isinstance(actual_output, list) or not isinstance(expected_output, list):
        return {"mrr": 0.0}
    relevant_set = set(str(r) for r in expected_output)
    if not relevant_set:
        return {"mrr": 1.0}
    for i, r in enumerate(actual_output):
        if str(r) in relevant_set:
            return {"mrr": 1.0 / (i + 1)}
    return {"mrr": 0.0}


def _search_relevance_score(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Composite relevance score: 0.4*precision@5 + 0.3*recall@5 + 0.3*ndcg@10."""
    p = _precision_at_k(case_input, actual_output, expected_output, {"k": 5})
    r = _recall_at_k(case_input, actual_output, expected_output, {"k": 5})
    n = _ndcg(case_input, actual_output, expected_output, {"k": 10})
    score = (
        0.4 * p.get("precision_at_k", 0) + 0.3 * r.get("recall_at_k", 0) + 0.3 * n.get("ndcg", 0)
    )
    return {"relevance_score": score}


# ---------------------------------------------------------------------------
# Classification Evaluators
# ---------------------------------------------------------------------------


def _accuracy(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Accuracy: fraction of correct predictions."""
    if expected_output is None:
        return {"accuracy": 0.0}
    return {"accuracy": 1.0 if str(actual_output) == str(expected_output) else 0.0}


def _classification_precision(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Binary precision for a single case (1.0 if correct positive, 0.0 otherwise).

    For aggregate precision, sum correct positives / total predicted positives.
    This per-case version uses the expected_labels for context.
    """
    expected_labels = metadata.get("expected_labels") or []
    if not expected_labels:
        acc = _accuracy(case_input, actual_output, expected_output, metadata)
        return {"classification_precision": acc.get("accuracy", 0.0)}
    actual = str(actual_output)
    expected = str(expected_output) if expected_output else ""
    if actual in [str(lbl) for lbl in expected_labels]:
        return {"classification_precision": 1.0 if actual == expected else 0.0}
    return {"classification_precision": 0.0}


def _classification_recall(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Per-case recall: 1.0 if the expected class was predicted."""
    if expected_output is None:
        return {"classification_recall": 0.0}
    return {"classification_recall": 1.0 if str(actual_output) == str(expected_output) else 0.0}


def _f1_score(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Per-case F1 (harmonic mean of precision and recall)."""
    p = _classification_precision(
        case_input,
        actual_output,
        expected_output,
        metadata,
    ).get("classification_precision", 0.0)
    r = _classification_recall(
        case_input,
        actual_output,
        expected_output,
        metadata,
    ).get("classification_recall", 0.0)
    if p + r == 0:
        return {"f1": 0.0}
    return {"f1": 2 * (p * r) / (p + r)}


# ---------------------------------------------------------------------------
# Fraud Evaluators
# ---------------------------------------------------------------------------


def _fraud_precision(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Per-case fraud detection precision."""
    return _accuracy(case_input, actual_output, expected_output, metadata)


def _fraud_recall(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Per-case fraud detection recall."""
    return _accuracy(case_input, actual_output, expected_output, metadata)


def _fraud_f1(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Per-case fraud F1."""
    return _f1_score(case_input, actual_output, expected_output, metadata)


def _false_positive_rate(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Per-case FPR: 1.0 if false positive (predicted fraud, actually safe)."""
    if expected_output is None:
        return {"false_positive_rate": 0.0}
    is_false_positive = str(actual_output) in (
        "fraud",
        "suspicious",
        "high_risk",
        "1",
        "True",
    ) and str(expected_output) not in ("fraud", "suspicious", "high_risk", "1", "True")
    return {"false_positive_rate": 1.0 if is_false_positive else 0.0}


def _false_negative_rate(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Per-case FNR: 1.0 if false negative (predicted safe, actually fraud)."""
    if expected_output is None:
        return {"false_negative_rate": 0.0}
    is_false_negative = str(actual_output) not in (
        "fraud",
        "suspicious",
        "high_risk",
        "1",
        "True",
    ) and str(expected_output) in ("fraud", "suspicious", "high_risk", "1", "True")
    return {"false_negative_rate": 1.0 if is_false_negative else 0.0}


# ---------------------------------------------------------------------------
# LLM Quality Evaluators (heuristic, clearly labeled)
# ---------------------------------------------------------------------------


def _llm_task_success(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Heuristic task success: non-empty output with expected structure."""
    if actual_output is None:
        return {"task_success": 0.0}
    output_str = str(actual_output).strip()
    if not output_str:
        return {"task_success": 0.0}
    if expected_output is not None:
        return {"task_success": 1.0 if output_str == str(expected_output).strip() else 0.5}
    return {"task_success": 0.8}


def _llm_relevance(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Heuristic relevance: keyword overlap between input and output."""
    if actual_output is None or case_input is None:
        return {"relevance": 0.0}
    input_words = set(str(case_input).lower().split())
    output_words = set(str(actual_output).lower().split())
    if not input_words:
        return {"relevance": 0.0}
    overlap = input_words & output_words
    return {"relevance": len(overlap) / len(input_words)}


def _llm_completeness(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Heuristic completeness: output covers expected content."""
    if actual_output is None or expected_output is None:
        return {"completeness": 0.0}
    expected_words = set(str(expected_output).lower().split())
    output_words = set(str(actual_output).lower().split())
    if not expected_words:
        return {"completeness": 1.0}
    covered = expected_words & output_words
    return {"completeness": len(covered) / len(expected_words)}


def _hallucination_rate(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Heuristic hallucination: output words not in input or expected (lower is better)."""
    if actual_output is None:
        return {"hallucination_rate": 0.0}
    input_words = set(str(case_input).lower().split()) if case_input else set()
    expected_words = set(str(expected_output).lower().split()) if expected_output else set()
    output_words = set(str(actual_output).lower().split())
    known = input_words | expected_words
    if not output_words:
        return {"hallucination_rate": 0.0}
    unknown = output_words - known
    return {"hallucination_rate": len(unknown) / len(output_words)}


def _structured_output_validity(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Check if output is valid JSON/structured data when expected."""
    if actual_output is None:
        return {"structured_output_validity": 0.0}
    import json

    output = str(actual_output).strip()
    if output.startswith("{") or output.startswith("["):
        try:
            json.loads(output)
            return {"structured_output_validity": 1.0}
        except (json.JSONDecodeError, ValueError):
            return {"structured_output_validity": 0.0}
    return {"structured_output_validity": 0.8}


# ---------------------------------------------------------------------------
# General Evaluators
# ---------------------------------------------------------------------------


def _exact_match(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Exact string match."""
    if expected_output is None:
        return {"exact_match": 0.0}
    return {"exact_match": 1.0 if str(actual_output) == str(expected_output) else 0.0}


def _contains(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Output contains expected substring."""
    if expected_output is None:
        return {"contains": 0.0}
    return {"contains": 1.0 if str(expected_output).lower() in str(actual_output).lower() else 0.0}


def _length_ratio(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Ratio of output length to expected length (clamped 0-1)."""
    if expected_output is None:
        return {"length_ratio": 0.0}
    expected_len = len(str(expected_output))
    actual_len = len(str(actual_output))
    if expected_len == 0:
        return {"length_ratio": 1.0 if actual_len == 0 else 0.0}
    ratio = min(actual_len / expected_len, 2.0) / 2.0
    return {"length_ratio": ratio}


# ---------------------------------------------------------------------------
# Prediction Evaluators
# ---------------------------------------------------------------------------


def _mae(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Mean Absolute Error (per-case)."""
    try:
        actual = float(actual_output)
        expected = float(expected_output)
        return {"mae": abs(actual - expected)}
    except (TypeError, ValueError):
        return {"mae": 0.0}


def _rmse(
    case_input: Any,
    actual_output: Any,
    expected_output: Any,
    metadata: dict,
) -> dict[str, float]:
    """Root Mean Square Error (per-case = absolute error)."""
    try:
        actual = float(actual_output)
        expected = float(expected_output)
        return {"rmse": abs(actual - expected)}
    except (TypeError, ValueError):
        return {"rmse": 0.0}


# ---------------------------------------------------------------------------
# Register all evaluators
# ---------------------------------------------------------------------------

# Search
register_evaluator("search.precision_at_k", _precision_at_k)
register_evaluator("search.recall_at_k", _recall_at_k)
register_evaluator("search.ndcg", _ndcg)
register_evaluator("search.mrr", _mrr)
register_evaluator("search.relevance_score", _search_relevance_score)

# Classification
register_evaluator("classification.accuracy", _accuracy)
register_evaluator("classification.precision", _classification_precision)
register_evaluator("classification.recall", _classification_recall)
register_evaluator("classification.f1", _f1_score)

# Fraud
register_evaluator("fraud.precision", _fraud_precision)
register_evaluator("fraud.recall", _fraud_recall)
register_evaluator("fraud.f1", _fraud_f1)
register_evaluator("fraud.false_positive_rate", _false_positive_rate)
register_evaluator("fraud.false_negative_rate", _false_negative_rate)

# LLM
register_evaluator("llm.task_success", _llm_task_success)
register_evaluator("llm.relevance", _llm_relevance)
register_evaluator("llm.completeness", _llm_completeness)
register_evaluator("llm.hallucination_rate", _hallucination_rate)
register_evaluator("llm.structured_output_validity", _structured_output_validity)

# General
register_evaluator("general.exact_match", _exact_match)
register_evaluator("general.contains", _contains)
register_evaluator("general.length_ratio", _length_ratio)

# Prediction
register_evaluator("prediction.mae", _mae)
register_evaluator("prediction.rmse", _rmse)
