#!/usr/bin/env python3
"""Run the pinned cognitive-skill A/B battery and export blinded scoring packets."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "experiments" / "cognitive-skills"
SKILLS = [
    "automaticity", "a-touch-of-grace", "critical-thinking",
    "context-course-correction", "good-faith-collaboration",
    "peer-review", "optionality", "software-literacy",
    "task-integrity", "verification-integrity",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/cognitive-skill-battery")
    parser.add_argument("--skills", nargs="*", choices=SKILLS, default=SKILLS)
    parser.add_argument("--qbatch-path", default=".vendor/q-batch-of-evidence")
    args = parser.parse_args()
    if not os.environ.get("AI_RUNTIME_API_KEY"):
        raise SystemExit("AI_RUNTIME_API_KEY is not set; refusing to substitute mock outputs for a real skill test.")
    qbatch = (ROOT / args.qbatch_path).resolve()
    if not (qbatch / ".git").exists():
        raise SystemExit(f"Pinned Q-Batch checkout not found: {qbatch}")
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not venv_python.exists():
        raise SystemExit("Runtime virtual environment not found; run setup_environment.py first.")
    runner_python = str(venv_python)
    output = (ROOT / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    index = []
    env = os.environ.copy()
    env["Q_BATCH_PATH"] = str(qbatch)
    env["AI_RUNTIME_API_KEY"] = os.environ["AI_RUNTIME_API_KEY"]

    for skill_id in args.skills:
        spec = SUITE / f"{skill_id}.json"
        rubric = SUITE / "rubrics" / f"{skill_id}.json"
        skill_root = output / skill_id
        run_dir = skill_root / "experiment"
        controller_dir.mkdir(parents=True, exist_ok=True)
        scorer_dir = skill_root / "scorer"
        controller_dir = skill_root / "controller"
        scorer_dir.mkdir(parents=True, exist_ok=True)
        controller_dir.mkdir(parents=True, exist_ok=True)
        run_spec = SUITE / f".{skill_id}-{secrets.token_hex(6)}.json"
        spec_doc = json.loads(spec.read_text(encoding="utf-8"))
        flip_labels = secrets.choice([False, True])
        for condition in spec_doc["conditions"]:
            if condition["id"] == "baseline":
                condition["label"] = "B" if flip_labels else "A"
            else:
                condition["label"] = "A" if flip_labels else "B"
        run_spec.write_text(json.dumps(spec_doc, indent=2) + "\\n", encoding="utf-8")
        snapshot = controller_dir / "run-spec.json"
        snapshot.write_text(run_spec.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run([
            runner_python, "-m", "ai_experiment_runtime", "run",
            "--spec", str(run_spec), "--output", str(run_dir), "--qbatch-path", str(qbatch),
        ], cwd=ROOT, env=env, check=True)
        report = run_dir / "reports" / "batch-report.json"
        packet = scorer_dir / "scoring-packet.json"
        private_key = controller_dir / "blind-key.json"
        subprocess.run([
            runner_python, "-m", "ai_experiment_runtime", "blind-export",
            "--report", str(report), "--spec", str(run_spec),
            "--packet", str(packet), "--private-key", str(private_key),
        ], cwd=ROOT, env=env, check=True)
        run_spec.unlink(missing_ok=True)\n        condition_key_copy = controller_dir / "condition-key.json"\n        condition_key_copy.write_text((run_dir / "controller" / "condition-key.json").read_text(encoding="utf-8"), encoding="utf-8")\n        rubric_copy = scorer_dir / "rubric.json"
        rubric_copy.write_text(rubric.read_text(encoding="utf-8"), encoding="utf-8")
        index.append({
            "skill_id": skill_id,
            "experiment_id": f"cognitive-{skill_id}",
            "report": str(report.relative_to(output)),
            "scoring_packet": str(packet.relative_to(output)),
            "rubric": str(rubric_copy.relative_to(output)),
            "private_key": str(private_key.relative_to(output)),\n            "condition_key": str(condition_key_copy.relative_to(output)),\n            "run_spec_snapshot": str(snapshot.relative_to(output)),
            "samples": 12,
        })
    (output / "index.json").write_text(json.dumps({
        "suite_revision": "fc530b6815eead24aa8655cbbb4bfe0dd8c9f666",
        "skills": index,
        "note": "Keep every controller/private-key directory away from scorers. Share only scorer/scoring-packet.json and scorer/rubric.json.",
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "skills_run": len(index)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
