from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_experiment_runtime.spec import load_experiment

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "experiments" / "cognitive-skills"
EXPECTED = {
    "automaticity", "a-touch-of-grace", "critical-thinking", "context-course-correction",
    "good-faith-collaboration", "peer-review", "optionality", "software-literacy",
    "task-integrity", "verification-integrity",
}
PINNED_SKILLS_REVISION = "fc530b6815eead24aa8655cbbb4bfe0dd8c9f666"


class CognitiveSkillSuiteTests(unittest.TestCase):
    def test_all_canonical_skills_have_independent_paired_experiments(self) -> None:
        specs = {path.stem: path for path in SUITE.glob("*.json")}
        self.assertEqual(set(specs), EXPECTED)
        for skill_id, path in specs.items():
            with self.subTest(skill=skill_id):
                experiment = load_experiment(path)
                self.assertEqual(experiment.experiment_id, f"cognitive-{skill_id}")
                self.assertEqual(len(experiment.tasks), 3)
                self.assertEqual(experiment.trials_per_task, 2)
                self.assertEqual({item.label for item in experiment.conditions}, {"A", "B"})
                baseline = next(item for item in experiment.conditions if item.condition_id == "baseline")
                intervention = next(item for item in experiment.conditions if item.condition_id == "skill-enabled")
                self.assertEqual(len(baseline.resources), 0)
                self.assertEqual(len(intervention.resources), 1)
                self.assertEqual(intervention.resources[0].path, f"../../.vendor/cognitive-interface-ai-skills/{skill_id}/SKILL.md")
                self.assertTrue(intervention.resources[0].content.strip())
                self.assertIn(PINNED_SKILLS_REVISION, path.read_text(encoding="utf-8"))

    def test_every_skill_has_a_predeclared_rubric(self) -> None:
        for skill_id in EXPECTED:
            with self.subTest(skill=skill_id):
                path = SUITE / "rubrics" / f"{skill_id}.json"
                rubric = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(rubric["skill_id"], skill_id)
                self.assertEqual(rubric["skill_revision"], PINNED_SKILLS_REVISION)
                self.assertGreaterEqual(len(rubric["criteria"]), 3)
                self.assertTrue(all(item["min_score"] < item["max_score"] for item in rubric["criteria"]))


if __name__ == "__main__":
    unittest.main()
