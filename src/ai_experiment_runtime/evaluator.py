"""Independent rubric evaluation using blinded, externally supplied scores."""
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


def evaluate_report(report_path: str | Path, rubric_path: str | Path,
                    scores_path: str | Path, blind_key_path: str | Path) -> dict[str, Any]:
    """Resolve blind IDs privately, then calculate descriptive paired differences.

    The scorer receives only the packet, rubric and opaque sample IDs. The private
    key is retained by the experiment controller and supplied only after scoring
    has been locked. This module never calls a model or infers scores from text.
    """
    report = _read_json(report_path)
    rubric = _read_json(rubric_path)
    score_doc = _read_json(scores_path)
    blind_key = _read_json(blind_key_path)

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
    if score_doc.get("experiment_id") != report.get("experiment_id") or blind_key.get("experiment_id") != report.get("experiment_id"):
        raise EvaluationError("experiment_id does not match report")
    if score_doc.get("report_spec_sha256") != report.get("spec_sha256") or blind_key.get("report_spec_sha256") != report.get("spec_sha256"):
        raise EvaluationError("report specification hash does not match")
    if score_doc.get("rubric_sha256") != _sha256(rubric):
        raise EvaluationError("scores rubric_sha256 does not match the rubric")
    if score_doc.get("blind_key_sha256") != _sha256(blind_key):
        raise EvaluationError("scores blind_key_sha256 does not match the private key")
    if not isinstance(score_doc.get("evaluator_id"), str) or not score_doc["evaluator_id"].strip():
        raise EvaluationError("scores must identify the evaluator")

    key_samples = blind_key.get("samples")
    if not isinstance(key_samples, dict):
        raise EvaluationError("private blind key is malformed")
    mapped_runs: dict[str, dict[str, Any]] = {}
    for blind_id, mapping in key_samples.items():
        if not isinstance(mapping, dict) or mapping.get("run_id") not in expected_runs:
            raise EvaluationError("private key references an unknown run")
        if mapping["run_id"] in mapped_runs:
            raise EvaluationError("private key maps multiple blind IDs to one run")
        mapped_runs[mapping["run_id"]] = mapping
    if set(mapped_runs) != set(expected_runs):
        raise EvaluationError("private key does not map every run exactly once")

    entries = score_doc.get("scores")
    if not isinstance(entries, list):
        raise EvaluationError("scores must be an array")
    by_run: dict[str, dict[str, float]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("blind_id") not in key_samples:
            raise EvaluationError("score entry references an unknown blind_id")
        blind_id = entry["blind_id"]
        run_id = key_samples[blind_id]["run_id"]
        if run_id in by_run:
            raise EvaluationError(f"duplicate score entry for blind_id: {blind_id}")
        values = entry.get("values")
        if not isinstance(values, dict) or set(values) != set(criterion_ids):
            raise EvaluationError(f"sample {blind_id} must have exactly one score for every rubric criterion")
        normalized: dict[str, float] = {}
        for criterion in criteria:
            value = values[criterion["id"]]
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value < criterion["min_score"] or value > criterion["max_score"]):
                raise EvaluationError(f"score {criterion['id']} for {blind_id} is outside its permitted range")
            normalized[criterion["id"]] = float(value)
        by_run[run_id] = normalized
    if set(by_run) != set(expected_runs):
        missing = sorted(set(expected_runs) - set(by_run))
        raise EvaluationError(f"missing scores for runs: {', '.join(missing)}")

    condition_key = blind_key.get("condition_key")
    if not isinstance(condition_key, dict) or set(condition_key.values()) != {"baseline", "skill-enabled"}:
        raise EvaluationError("private key must map A/B labels to baseline and skill-enabled")
    condition_label = {condition_id: label for label, condition_id in condition_key.items()}
    grouped: dict[tuple[str, int], dict[str, str]] = {}
    for run_id, run in expected_runs.items():
        key = (run["task_id"], run["trial"])
        grouped.setdefault(key, {})[run["condition_label"]] = run_id
    pairs = []
    for (task_id, trial), pair in sorted(grouped.items()):
        if set(pair) != {"A", "B"}:
            raise EvaluationError(f"task {task_id} trial {trial} is not a complete A/B pair")
        baseline_run = pair[condition_label["baseline"]]
        skill_run = pair[condition_label["skill-enabled"]]
        pairs.append({
            "task_id": task_id, "trial": trial,
            "scores_baseline": by_run[baseline_run],
            "scores_skill_enabled": by_run[skill_run],
            "delta_skill_minus_baseline": {
                key: by_run[skill_run][key] - by_run[baseline_run][key] for key in criterion_ids
            },
        })
    summaries = {}
    for criterion_id in criterion_ids:
        baseline_label = condition_label["baseline"]
        skill_label = condition_label["skill-enabled"]
        values_baseline = [by_run[run_id][criterion_id] for run_id, run in expected_runs.items() if run["condition_label"] == baseline_label]
        values_skill = [by_run[run_id][criterion_id] for run_id, run in expected_runs.items() if run["condition_label"] == skill_label]
        deltas = [pair["delta_skill_minus_baseline"][criterion_id] for pair in pairs]
        summaries[criterion_id] = {
            "mean_baseline": sum(values_baseline) / len(values_baseline),
            "mean_skill_enabled": sum(values_skill) / len(values_skill),
            "mean_paired_delta_skill_minus_baseline": sum(deltas) / len(deltas),
            "paired_observations": len(deltas),
        }
    return {
        "evaluation_version": "1.0", "experiment_id": report["experiment_id"],
        "report_spec_sha256": report["spec_sha256"], "rubric_sha256": _sha256(rubric),
        "evaluator_id": score_doc["evaluator_id"], "scoring_method": "EXTERNAL_BLINDED_SCORES_ONLY",
        "blind_key_sha256": _sha256(blind_key),
        "revealed_condition_mapping": condition_key,
        "interpretation": "Descriptive paired score differences only; no statistical significance or causal claim is inferred.",
        "criteria": summaries, "paired_results": pairs,
    }
