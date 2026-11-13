from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_experiment_runtime.spec import SpecError, load_experiment


class ExperimentSpecTests(unittest.TestCase):
    def _write_spec(self, folder: Path, doc: dict) -> Path:
        path = folder / "experiment.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def _valid(self) -> dict:
        return {
            "schema_version": "1.0",
            "experiment_id": "unit-test",
            "title": "Unit test",
            "provider": {"type": "mock", "model": "fixture"},
            "tasks": [{"id": "task-1", "prompt": "Test input"}],
            "conditions": [
                {"id": "baseline", "label": "A", "mock_responses": {"task-1": "A"}},
                {"id": "intervention", "label": "B", "mock_responses": {"task-1": "B"}},
            ],
        }

    def test_loads_valid_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_spec(Path(tmp), self._valid())
            loaded = load_experiment(path)
            self.assertEqual(loaded.experiment_id, "unit-test")
            self.assertEqual([c.label for c in loaded.conditions], ["A", "B"])

    def test_rejects_duplicate_task_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._valid()
            doc["tasks"].append({"id": "task-1", "prompt": "duplicate"})
            with self.assertRaises(SpecError):
                load_experiment(self._write_spec(Path(tmp), doc))

    def test_rejects_nonlocal_plain_http_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            doc = self._valid()
            doc["provider"] = {"type": "openai-compatible", "model": "x", "base_url": "http://example.com/v1"}
            with self.assertRaises(SpecError):
                load_experiment(self._write_spec(Path(tmp), doc))

    def test_hash_changes_when_resource_bytes_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            resource = folder / "skill.md"
            resource.write_text("first", encoding="utf-8")
            doc = self._valid()
            doc["conditions"][1]["resources"] = [{"name": "skill", "path": "skill.md"}]
            path = self._write_spec(folder, doc)
            first = load_experiment(path).conditions[1].config_sha256
            resource.write_text("second", encoding="utf-8")
            second = load_experiment(path).conditions[1].config_sha256
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
