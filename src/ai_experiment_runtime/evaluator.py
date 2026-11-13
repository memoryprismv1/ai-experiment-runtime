"""Independent, rubric-based evaluation of completed experiment outputs."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


class EvaluationError(ValueError):
    """Rubric or scoring data is incomplete, inconsistent, or out of range."""


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read JSON input: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationError("JSON input must be an object")
    return value


def _sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def evaluate_report(report_path: str | Path, rubric_path: str | Path, scores_path: str | Path) -> dict[str, Any]:
    """Score already-recorded runs using externally supplied rubric assessments.

    This function never calls a model and never infers a score from the response.
    Scores may be entered by a blinded human evaluator or imported from a separate
    evaluation system. The evaluator must keep the A/B key concealed until scoring
    is complete.
    """
    report = _read_json(report_path)
    rubric = _read_json(rubric_path)
    score_doc = _read_json(scores_path)

    if report.get("status") != "PASS":
        raise EvaluationError("only a Q-Batch-verified PASS report can be evaluated")
    if report.get("classification") != "EXPERIMENT_EXECUTION_AND_QBATCH_INSTRUMENTATION_VERIFICATION_ONLY":
        raise EvaluationError("unsupported report classification")

    criteria = rubric.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise EvaluationError("rubric.criteria must be a non-empty array")
    criterion_ids: list[str] = []
    for item in criteria:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise EvaluationError("each rubric criterion needs a non-empty id")
        if item["id"] in criterion_ids:
            raise EvaluationError(f"duplicate rubric criterion: {item['id']}")
        low, high = item.get("min_score"), item.get("max_score")
        if (not isinstance(low, (int, float)) or isinstance(low, bool)
                or not isinstance(high, (int, float)) or isinstance(high, bool)
                or not math.isfinite(low) or not math.isfinite(high) or low >= high):
            raise EvaluationError(f"criterion {item['id']} needs finite min_score < max_score")
        if not isinstance(item.get("description"), str) or not item["description"].strip():
            raise EvaluationError(f"criterion {item['id']} needs a description")
        criterion_ids.append(item["id"])

    expected_runs = {item["run_id"]: item for item in report.get("run_results", [])}
    if not expected_runs or any(item.get("status") != "COMPLETED" for item in expected_runs.values()):
        raise EvaluationError("report must contain completed runs only")
    if len(expected_runs) != report.get("run_count"):
        raise EvaluationError("report run_count does not match run_results")

    if score_doc.get("experiment_id") != report.get("experiment_id"):
        raise EvaluationError("scores experiment_id does not match report")
    if score_doc.get("report_spec_sha256") != report.get("spec_sha256"):
        raise EvaluationError("scores report_spec_sha256 does not match report")
    if score_doc.get("rubric_sha256") != _sha256(rubric):
        raise EvaluationError("scores rubric_sha256 does not match the rubric")
    if not isinstance(score_doc.get("evaluator_id"), str) or not score_doc["evaluator_id"].strip():
        raise EvaluationError("scores must identify the evaluator")

    entries = score_doc.get("scores")
    if not isinstance(entries, list):
        raise EvaluationError("scores must be an array")
    by_run: dict[str, dict[str, float]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("run_id") not in expected_runs:
            raise EvaluationError("score entry references an unknown run_id")
        run_id = entry["run_id"]
        if run_id in by_run:
            raise EvaluationError(f"duplicate score entry for run: {run_id}")
        values = entry.get("values")
        if not isinstance(values, dict) or set(values) != set(criterion_ids):
            raise EvaluationError(f"run {run_id} must have exactly one score for every rubric criterion")
        normalized: dict[str, float] = {}
        for criterion in criteria:
            value = values[criterion["id"]]
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value < criterion["min_score"] or value > criterion["max_score"]):
                raise EvaluationError(f"score {criterion['id']} for {run_id} is outside its permitted range")
            normalized[criterion["id"]] = float(value)
        by_run[run_id] = normalized
    if set(by_run) != set(expected_runs):
        missing = sorted(set(expected_runs) - set(by_run))
        raise EvaluationError(f"missing scores for runs: {', '.join(missing)}")

    grouped: dict[tuple[str, int], dict[str, str]] = {}
    for run_id, run in expected_runs.items():
        key = (run["task_id"], run["trial"])
        grouped.setdefault(key, {})[run["condition_label"]] = run_id
    pairs = []
    for (task_id, trial), pair in sorted(grouped.items()):
        if set(pair) != {"A", "B"}:
            raise EvaluationError(f"task {task_id} trial {trial} is not a complete A/B pair")
        pairs.append({
            "task_id": task_id,
            "trial": trial,
            "scores_A": by_run[pair["A"]],
            "scores_B": by_run[pair["B"]],
            "delta_B_minus_A": {key: by_run[pair["B"]][key] - by_run[pair["A"]][key] for key in criterion_ids},
        })

    summaries = {}
    for criterion_id in criterion_ids:
        values_a = [by_run[run_id][criterion_id] for run_id, run in expected_runs.items() if run["condition_label"] == "A"]
        values_b = [by_run[run_id][criterion_id] for run_id, run in expected_runs.items() if run["condition_label"] == "B"]
        deltas = [pair["delta_B_minus_A"][criterion_id] for pair in pairs]
        summaries[criterion_id] = {
            "mean_A": sum(values_a) / len(values_a),
            "mean_B": sum(values_b) / len(values_b),
            "mean_paired_delta_B_minus_A": sum(deltas) / len(deltas),
            "paired_observations": len(deltas),
        }

    return {
        "evaluation_version": "1.0",
        "experiment_id": report["experiment_id"],
        "report_spec_sha256": report["spec_sha256"],
        "rubric_sha256": _sha256(rubric),
        "evaluator_id": score_doc["evaluator_id"],
        "scoring_method": "EXTERNAL_SCORES_ONLY",
        "interpretation": "Descriptive paired score differences only; no statistical significance or causal claim is inferred.",
        "criteria": summaries,
        "paired_results": pairs,
    }
