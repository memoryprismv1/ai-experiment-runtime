from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ai_experiment_runtime.evaluator import EvaluationError, evaluate_report


class IndependentEvaluationTests(unittest.TestCase):
    def _write(self, folder: Path, name: str, value: dict) -> Path:
        path = folder / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_blinded_external_scores_produce_paired_descriptive_deltas(self) -> None:
        rubric = {"criteria": [
            {"id": "accuracy", "description": "Factual correctness", "min_score": 0, "max_score": 4},
            {"id": "clarity", "description": "Clarity of response", "min_score": 1, "max_score": 5},
        ]}
        report = {
            "status": "PASS",
            "classification": "EXPERIMENT_EXECUTION_AND_QBATCH_INSTRUMENTATION_VERIFICATION_ONLY",
            "experiment_id": "demo",
            "spec_sha256": "spec-hash",
            "run_count": 4,
            "run_results": [
                {"run_id": "a1", "status": "COMPLETED", "task_id": "t1", "trial": 1, "condition_label": "A"},
                {"run_id": "b1", "status": "COMPLETED", "task_id": "t1", "trial": 1, "condition_label": "B"},
                {"run_id": "a2", "status": "COMPLETED", "task_id": "t2", "trial": 1, "condition_label": "A"},
                {"run_id": "b2", "status": "COMPLETED", "task_id": "t2", "trial": 1, "condition_label": "B"},
            ],
        }
        rubric_bytes = json.dumps(rubric, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        scores = {
            "experiment_id": "demo",
            "report_spec_sha256": "spec-hash",
            "rubric_sha256": hashlib.sha256(rubric_bytes).hexdigest(),
            "evaluator_id": "human-reviewer-01",
            "scores": [
                {"run_id": "a1", "values": {"accuracy": 2, "clarity": 3}},
                {"run_id": "b1", "values": {"accuracy": 4, "clarity": 4}},
                {"run_id": "a2", "values": {"accuracy": 3, "clarity": 2}},
                {"run_id": "b2", "values": {"accuracy": 3, "clarity": 5}},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            result = evaluate_report(
                self._write(folder, "report.json", report),
                self._write(folder, "rubric.json", rubric),
                self._write(folder, "scores.json", scores),
            )
        self.assertEqual(result["scoring_method"], "EXTERNAL_SCORES_ONLY")
        self.assertEqual(result["criteria"]["accuracy"]["mean_paired_delta_B_minus_A"], 1.0)
        self.assertEqual(result["criteria"]["clarity"]["mean_paired_delta_B_minus_A"], 2.0)
        self.assertEqual(len(result["paired_results"]), 2)

    def test_rejects_missing_run_score(self) -> None:
        rubric = {"criteria": [{"id": "quality", "description": "Quality", "min_score": 0, "max_score": 5}]}
        report = {
            "status": "PASS",
            "classification": "EXPERIMENT_EXECUTION_AND_QBATCH_INSTRUMENTATION_VERIFICATION_ONLY",
            "experiment_id": "demo", "spec_sha256": "hash", "run_count": 2,
            "run_results": [
                {"run_id": "a", "status": "COMPLETED", "task_id": "t", "trial": 1, "condition_label": "A"},
                {"run_id": "b", "status": "COMPLETED", "task_id": "t", "trial": 1, "condition_label": "B"},
            ],
        }
        rubric_hash = hashlib.sha256(json.dumps(rubric, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        scores = {"experiment_id": "demo", "report_spec_sha256": "hash", "rubric_sha256": rubric_hash,
                  "evaluator_id": "reviewer", "scores": [{"run_id": "a", "values": {"quality": 3}}]}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaisesRegex(EvaluationError, "missing scores"):
                evaluate_report(self._write(folder, "r.json", report), self._write(folder, "rubric.json", rubric),
                                self._write(folder, "s.json", scores))

    def test_rejects_non_pass_execution_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaisesRegex(EvaluationError, "PASS report"):
                evaluate_report(self._write(folder, "r.json", {"status": "FAIL"}),
                                self._write(folder, "rubric.json", {}),
                                self._write(folder, "s.json", {}))


if __name__ == "__main__":
    unittest.main()
