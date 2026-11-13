"""Create scorer-facing packets without exposing condition identity or prompts used as resources."""
from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any


class BlindingError(ValueError):
    """The report cannot be exported as a complete blinded scoring packet."""


def _read(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BlindingError(f"cannot read JSON input: {exc}") from exc
    if not isinstance(value, dict):
        raise BlindingError("JSON input must be an object")
    return value


def export_blinded_packet(report_path: str | Path, spec_path: str | Path,
                          packet_path: str | Path, key_path: str | Path) -> dict[str, Any]:
    report = _read(report_path)
    spec = _read(spec_path)
    if report.get("status") != "PASS":
        raise BlindingError("only a Q-Batch-verified PASS report can be blinded")
    if report.get("spec_sha256") is None or report.get("experiment_id") != spec.get("experiment_id"):
        raise BlindingError("report and experiment specification do not match")
    from .hashing import canonical_json, sha256_bytes
    if sha256_bytes(canonical_json(spec)) != report["spec_sha256"]:
        raise BlindingError("experiment specification hash does not match report")

    tasks = {item["id"]: item["prompt"] for item in spec.get("tasks", [])}
    results = report.get("run_results", [])
    if not results or len(results) != report.get("run_count"):
        raise BlindingError("report run_results are incomplete")
    packet_samples = []
    key_samples = {}
    seen = set()
    for run in results:
        if run.get("status") != "COMPLETED" or run.get("task_id") not in tasks or not isinstance(run.get("response"), str):
            raise BlindingError("every run must have a completed response and a matching task prompt")
        run_id = run["run_id"]
        if run_id in seen:
            raise BlindingError(f"duplicate run_id: {run_id}")
        seen.add(run_id)
        blind_id = "sample-" + secrets.token_hex(8)
        packet_samples.append({
            "blind_id": blind_id,
            "task_id": run["task_id"],
            "trial": run["trial"],
            "prompt": tasks[run["task_id"]],
            "response": run["response"],
        })
        key_samples[blind_id] = {
            "run_id": run_id,
            "condition_label": run["condition_label"],
            "task_id": run["task_id"],
            "trial": run["trial"],
        }
    groups: dict[tuple[str, int], set[str]] = {}
    for item in results:
        groups.setdefault((item["task_id"], item["trial"]), set()).add(item["condition_label"])
    if any(labels != {"A", "B"} for labels in groups.values()):
        raise BlindingError("report contains an incomplete A/B pair")

    report_file = Path(report_path).resolve()\n    run_root = report_file.parent.parent if report_file.parent.name == "reports" else report_file.parent
    condition_key_path = run_root / "controller" / "condition-key.json"
    condition_key = _read(condition_key_path)
    if set(condition_key) != {"A", "B"} or set(condition_key.values()) != {"baseline", "skill-enabled"}:
        raise BlindingError("controller condition key must map A/B to baseline and skill-enabled")

    # Shuffle the scorer-facing packet independently of execution order.
    import random
    random.SystemRandom().shuffle(packet_samples)
    packet = {
        "packet_version": "1.0",
        "experiment_id": report["experiment_id"],
        "report_spec_sha256": report["spec_sha256"],
        "instructions": "Score each response independently against the supplied rubric. Do not infer condition identity. Return scores keyed by blind_id.",
        "samples": packet_samples,
    }
    key = {
        "key_version": "1.0",
        "experiment_id": report["experiment_id"],
        "report_spec_sha256": report["spec_sha256"],
        "samples": key_samples,\n        "condition_key": condition_key,
    }
    packet_target, key_target = Path(packet_path), Path(key_path)
    if packet_target.resolve() == key_target.resolve():
        raise BlindingError("scoring packet and private key must be different files")
    packet_target.parent.mkdir(parents=True, exist_ok=True)
    key_target.parent.mkdir(parents=True, exist_ok=True)
    packet_target.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    key_target.write_text(json.dumps(key, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"experiment_id": report["experiment_id"], "samples": len(packet_samples),
            "packet_path": str(packet_target), "private_key_path": str(key_target)}
