#!/usr/bin/env python3
"""Run the pinned cognitive-skill A/B battery and export blinded scoring packets."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
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
    parser.add_argument("--model", default="qwen2.5:7b", help="Local Ollama model tag")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1", help="OpenAI-compatible local inference endpoint")
    args = parser.parse_args()
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
    failed_skills = []
    env = os.environ.copy()
    env["Q_BATCH_PATH"] = str(qbatch)

    for skill_id in args.skills:
        spec = SUITE / f"{skill_id}.json"
        rubric = SUITE / "rubrics" / f"{skill_id}.json"
        skill_root = output / skill_id
        run_dir = skill_root / "experiment"
        scorer_dir = skill_root / "scorer"
        controller_dir = skill_root / "controller"
        scorer_dir.mkdir(parents=True, exist_ok=True)
        controller_dir.mkdir(parents=True, exist_ok=True)

        # Randomise which opaque A/B label receives the intervention. The
        # scorer sees neither this mapping nor the skill resource prompt.
        run_spec = SUITE / f".{skill_id}-{secrets.token_hex(6)}.json"
        spec_doc = json.loads(spec.read_text(encoding="utf-8"))
        # Run entirely against a local OpenAI-compatible inference server (Ollama by default).
        # No API credential or paid hosted inference is required.
        spec_doc["provider"]["type"] = "openai-compatible"
        spec_doc["provider"]["base_url"] = args.base_url.rstrip("/")
        spec_doc["provider"]["model"] = args.model
        spec_doc["provider"].pop("api_key_env", None)
        flip_labels = secrets.choice([False, True])
        for condition in spec_doc["conditions"]:
            condition["label"] = (
                ("B" if flip_labels else "A") if condition["id"] == "baseline"
                else ("A" if flip_labels else "B")
            )
        run_spec.write_text(json.dumps(spec_doc, indent=2) + "\n", encoding="utf-8")
        snapshot = controller_dir / "run-spec.json"
        snapshot.write_text(run_spec.read_text(encoding="utf-8"), encoding="utf-8")

        run_process = subprocess.run([
            runner_python, "-m", "ai_experiment_runtime", "run",
            "--spec", str(run_spec), "--output", str(run_dir), "--qbatch-path", str(qbatch),
        ], cwd=ROOT, env=env, check=False)

        report = run_dir / "reports" / "batch-report.json"
        if run_process.returncode != 0:
            failed_skills.append(skill_id)
            report_doc = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
            diagnostics = [
                {"condition": item.get("condition_label"), "task": item.get("task_id"),
                 "trial": item.get("trial"), "error": item.get("error")}
                for item in report_doc.get("run_results", []) if item.get("error")
            ]
            print(json.dumps({"skill_id": skill_id, "status": "FAILED", "provider_errors": diagnostics}, indent=2))
            condition_key_copy = controller_dir / "condition-key.json"
            key_source = run_dir / "controller" / "condition-key.json"
            if key_source.exists():
                condition_key_copy.write_text(key_source.read_text(encoding="utf-8"), encoding="utf-8")
            index.append({
                "skill_id": skill_id, "status": "FAILED",
                "experiment_id": f"cognitive-{skill_id}",
                "report": str(report.relative_to(output)) if report.exists() else None,
                "private_key": None,
                "condition_key": str(condition_key_copy.relative_to(output)) if condition_key_copy.exists() else None,
                "run_spec_snapshot": str(snapshot.relative_to(output)), "samples": 12,
            })
            run_spec.unlink(missing_ok=True)
            continue
        packet = scorer_dir / "scoring-packet.json"
        private_key = controller_dir / "blind-key.json"
        subprocess.run([
            runner_python, "-m", "ai_experiment_runtime", "blind-export",
            "--report", str(report), "--spec", str(run_spec),
            "--packet", str(packet), "--private-key", str(private_key),
        ], cwd=ROOT, env=env, check=True)
        run_spec.unlink(missing_ok=True)

        condition_key_copy = controller_dir / "condition-key.json"
        condition_key_copy.write_text(
            (run_dir / "controller" / "condition-key.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        rubric_copy = scorer_dir / "rubric.json"
        rubric_copy.write_text(rubric.read_text(encoding="utf-8"), encoding="utf-8")
        index.append({
            "status": "COMPLETED",
            "skill_id": skill_id,
            "experiment_id": f"cognitive-{skill_id}",
            "report": str(report.relative_to(output)),
            "scoring_packet": str(packet.relative_to(output)),
            "rubric": str(rubric_copy.relative_to(output)),
            "private_key": str(private_key.relative_to(output)),
            "condition_key": str(condition_key_copy.relative_to(output)),
            "run_spec_snapshot": str(snapshot.relative_to(output)),
            "samples": 12,
        })

    (output / "index.json").write_text(json.dumps({
        "suite_revision": "fc530b6815eead24aa8655cbbb4bfe0dd8c9f666",
        "inference": {"provider": "local-openai-compatible", "base_url": args.base_url, "model": args.model},
        "skills": index,
        "note": "Keep every controller/private-key directory away from scorers. Share only scorer/scoring-packet.json and scorer/rubric.json.",
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "skills_run": len(index), "failed_skills": failed_skills}, indent=2))
    return 1 if failed_skills else 0


if __name__ == "__main__":
    raise SystemExit(main())
