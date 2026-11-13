from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ai_experiment_runtime.blinding import export_blinded_packet
from ai_experiment_runtime.evaluator import EvaluationError, evaluate_report


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class IndependentEvaluationTests(unittest.TestCase):
    def _write(self, folder: Path, name: str, value: dict) -> Path:
        path = folder / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _fixture(self, folder: Path):
        rubric = {"criteria": [
            {"id": "accuracy", "description": "Factual correctness", "min_score": 0, "max_score": 4},
            {"id": "clarity", "description": "Clarity of response", "min_score": 1, "max_score": 5},
        ]}
        spec = {"experiment_id": "demo", "tasks": [
            {"id": "t1", "prompt": "Task one"}, {"id": "t2", "prompt": "Task two"}]}
        report = {
            "status": "PASS",
            "classification": "EXPERIMENT_EXECUTION_AND_QBATCH_INSTRUMENTATION_VERIFICATION_ONLY",
            "experiment_id": "demo", "spec_sha256": canonical_hash(spec), "run_count": 4,
            "run_results": [
                {"run_id": "a1", "status": "COMPLETED", "task_id": "t1", "trial": 1, "condition_label": "A", "response": "answer a1"},
                {"run_id": "b1", "status": "COMPLETED", "task_id": "t1", "trial": 1, "condition_label": "B", "response": "answer b1"},
                {"run_id": "a2", "status": "COMPLETED", "task_id": "t2", "trial": 1, "condition_label": "A", "response": "answer a2"},
                {"run_id": "b2", "status": "COMPLETED", "task_id": "t2", "trial": 1, "condition_label": "B", "response": "answer b2"},
            ],
        }
        report_path = self._write(folder, "report.json", report)
        spec_path = self._write(folder, "spec.json", spec)
        rubric_path = self._write(folder, "rubric.json", rubric)
        packet_path, key_path = folder / "scorer" / "packet.json", folder / "controller" / "blind-key.json"
        condition_key_path = folder / "controller" / "condition-key.json"
        condition_key_path.parent.mkdir(parents=True, exist_ok=True)
        condition_key_path.write_text(json.dumps({"A": "baseline", "B": "skill-enabled"}))
        export_blinded_packet(report_path, spec_path, packet_path, key_path)
        packet = json.loads(packet_path.read_text())
        key = json.loads(key_path.read_text())
        scores = {
            "experiment_id": "demo",
            "report_spec_sha256": report["spec_sha256"],
            "rubric_sha256": canonical_hash(rubric),
            "blind_key_sha256": canonical_hash(key),
            "evaluator_id": "human-reviewer-01",
            "scores": [
                {"blind_id": blind_id, "values": {
                    "accuracy": {"a1": 2, "b1": 4, "a2": 3, "b2": 3}[mapping["run_id"]],
                    "clarity": {"a1": 3, "b1": 4, "a2": 2, "b2": 5}[mapping["run_id"]],
                }}
                for blind_id, mapping in key["samples"].items()
            ],
        }
        scores_path = self._write(folder, "scores.json", scores)
        return report_path, rubric_path, scores_path, key_path, packet_path, key

    def test_blinded_external_scores_produce_paired_descriptive_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report, rubric, scores, key_path, packet_path, key = self._fixture(folder)
            packet = json.loads(packet_path.read_text())
            self.assertNotIn("condition_label", packet["samples"][0])
            self.assertNotIn("skill", json.dumps(packet).lower())
            result = evaluate_report(report, rubric, scores, key_path)
        self.assertEqual(result["scoring_method"], "EXTERNAL_BLINDED_SCORES_ONLY")
        self.assertEqual(result["criteria"]["accuracy"]["mean_paired_delta_skill_minus_baseline"], 1.0)
        self.assertEqual(result["criteria"]["clarity"]["mean_paired_delta_skill_minus_baseline"], 2.0)
        self.assertEqual(len(result["paired_results"]), 2)

    def test_rejects_missing_blind_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report, rubric, scores, key_path, _, _ = self._fixture(folder)
            score_doc = json.loads(scores.read_text())
            score_doc["scores"].pop()
            scores.write_text(json.dumps(score_doc))
            with self.assertRaisesRegex(EvaluationError, "missing scores"):
                evaluate_report(report, rubric, scores, key_path)

    def test_rejects_tampered_blind_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report, rubric, scores, key_path, _, _ = self._fixture(folder)
            key = json.loads(key_path.read_text())
            key["samples"].pop(next(iter(key["samples"])))
            key_path.write_text(json.dumps(key))
            with self.assertRaisesRegex(EvaluationError, "blind_key_sha256"):
                evaluate_report(report, rubric, scores, key_path)

    def test_rejects_non_pass_execution_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report, rubric, scores, key_path, _, _ = self._fixture(folder)
            report_doc = json.loads(report.read_text())
            report_doc["status"] = "FAIL"
            report.write_text(json.dumps(report_doc))
            with self.assertRaisesRegex(EvaluationError, "PASS report"):
                evaluate_report(report, rubric, scores, key_path)


if __name__ == "__main__":
    unittest.main()
