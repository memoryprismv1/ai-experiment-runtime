#!/usr/bin/env python3
"""Run one baseline/intervention inference pair and require Q-Batch PASS before the battery."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "experiments" / "cognitive-skills"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--qbatch-path", default=".vendor/q-batch-of-evidence")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    args = parser.parse_args()

    qbatch = (ROOT / args.qbatch_path).resolve()
    if not (qbatch / ".git").exists():
        raise SystemExit(f"Pinned Q-Batch checkout not found: {qbatch}")
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        raise SystemExit("Runtime virtual environment is missing")

    spec_path = SUITE / f"{args.skill}.json"
    spec_doc = json.loads(spec_path.read_text(encoding="utf-8"))
    if len(spec_doc.get("tasks", [])) < 1 or len(spec_doc.get("conditions", [])) != 2:
        raise SystemExit("Preflight requires at least one task and exactly two conditions")

    # Smoke one exact task through both conditions on the same model and
    # runner hardware planned for the full battery. Abort on any failure.
    spec_doc["tasks"] = spec_doc["tasks"][:1]
    spec_doc["trials_per_task"] = 1
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

    output = (ROOT / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    temporary_spec = SUITE / f".{args.skill}-preflight-{secrets.token_hex(6)}.json"
    temporary_spec.write_text(json.dumps(spec_doc, indent=2) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["Q_BATCH_PATH"] = str(qbatch)
    run_dir = output / "experiment"
    try:
        completed = subprocess.run([
            str(python), "-m", "ai_experiment_runtime", "run",
            "--spec", str(temporary_spec), "--output", str(run_dir),
            "--qbatch-path", str(qbatch),
        ], cwd=ROOT, env=env, check=False)
    finally:
        temporary_spec.unlink(missing_ok=True)

    report_path = run_dir / "reports" / "batch-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    runs = report.get("run_results", [])
    latencies = [item.get("latency_ms") for item in runs]
    summary = {
        "skill_id": args.skill,
        "model": args.model,
        "task_id": spec_doc["tasks"][0]["id"],
        "expected_runs": 2,
        "completed_runs": report.get("completed_trials"),
        "error": None if report_path.exists() else "Preflight did not produce a batch report",
        "failed_runs": report.get("failed_trials"),
        "qbatch_validated_runs": report.get("qbatch_validated_runs"),
        "qbatch_pair_checks_passed": report.get("qbatch_pair_checks_passed"),
        "qbatch_pair_checks_failed": report.get("qbatch_pair_checks_failed"),
        "latency_ms_by_label": {
            item.get("condition_label"): item.get("latency_ms") for item in runs
        },
        "status": "PASS" if report_path.exists() and completed.returncode == 0
            and report.get("status") == "PASS"
            and report.get("run_count") == 2
            and report.get("completed_trials") == 2
            and report.get("failed_trials") == 0
            and report.get("qbatch_validated_runs") == 2
            and report.get("qbatch_pair_checks_passed") == 1
            and report.get("qbatch_pair_checks_failed") == 0
            and len(latencies) == 2
            and all(isinstance(value, (int, float)) and value > 0 for value in latencies)
            and all(isinstance(item.get("response"), str) and item["response"].strip() for item in runs)
            else "FAIL",
    }
    (output / "preflight-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
