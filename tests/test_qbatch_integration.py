from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ai_experiment_runtime.runner import run_experiment
from ai_experiment_runtime.qbatch import load_qbatch

ROOT = Path(__file__).resolve().parents[1]
Q_BATCH_PATH = os.environ.get("Q_BATCH_PATH")


@unittest.skipUnless(Q_BATCH_PATH, "Q_BATCH_PATH is set in the pinned Q-Batch CI job")
class QBatchIntegrationTests(unittest.TestCase):
    def test_synthetic_pair_is_verified_by_qbatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "batch"
            report = run_experiment(ROOT / "examples" / "deterministic-pair.json", output, Q_BATCH_PATH)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["run_count"], 4)
            self.assertEqual(report["qbatch_validated_runs"], 4)
            self.assertEqual(report["qbatch_pair_checks_passed"], 2)
            self.assertIn("NOT_PERFORMED", report["quality_scoring"])

    def test_qbatch_verifier_rejects_tampered_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "batch"
            report = run_experiment(ROOT / "examples" / "deterministic-pair.json", output, Q_BATCH_PATH)
            run_dir = Path(report["run_results"][0]["run_dir"])
            artifact = next((run_dir / "artifacts").glob("*model-response.txt"))
            artifact.write_text("tampered", encoding="utf-8")
            _, _, validators = load_qbatch(Q_BATCH_PATH)
            with self.assertRaises(Exception):
                validators[0](run_dir)


if __name__ == "__main__":
    unittest.main()
