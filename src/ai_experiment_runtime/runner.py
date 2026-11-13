"""Execute isolated trials and preserve Q-Batch-verifiable evidence."""
from __future__ import annotations

import json
import platform
import random
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import canonical_json, sha256_bytes
from .providers import ProviderError, call_provider
from .qbatch import load_qbatch
from .spec import LoadedCondition, LoadedExperiment, load_experiment

SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe(value: str) -> str:
    return SAFE_ID.sub("-", value).strip("-.") or "item"


def _effective_system_prompt(experiment: LoadedExperiment, condition: LoadedCondition) -> str:
    pieces = [experiment.base_system_prompt]
    if condition.system_instruction.strip():
        pieces.append("CONDITION-SPECIFIC INSTRUCTION\n" + condition.system_instruction)
    for resource in condition.resources:
        pieces.append(f"RESOURCE: {resource.name}\n--- BEGIN RESOURCE ---\n{resource.content}\n--- END RESOURCE ---")
    return "\n\n".join(pieces)


def _run_one(
    experiment: LoadedExperiment,
    condition: LoadedCondition,
    task: dict[str, str],
    trial: int,
    output_root: Path,
    qbatch_path: str | Path | None,
    execution_order_index: int,
    randomization_seed: int,
) -> dict[str, Any]:
    TestingLogger, versions, _ = load_qbatch(qbatch_path)
    logger_version, schema_version, qbatch_utc_now = versions
    run_id = f"{experiment.experiment_id}-{condition.label}-{_safe(task['id'])}-r{trial:02d}"
    run_dir = output_root / "runs" / condition.label / f"{_safe(task['id'])}-r{trial:02d}"
    workspace = output_root / "workspaces" / condition.label / f"{_safe(task['id'])}-r{trial:02d}"
    workspace.mkdir(parents=True, exist_ok=False)

    provider = experiment.provider
    model_record = {"provider": provider["type"], "model_id": provider["model"]}
    environment = {
        "runtime": "ai-experiment-runtime",
        "runtime_version": "0.1.0",
        "python": platform.python_version(),
        "execution": "isolated_trial_workspace_no_agent_code_execution",
    }
    resource_limits = {
        "trials_per_task": experiment.trials_per_task,
        "randomization_seed": randomization_seed,
        "provider_timeout_seconds": provider.get("timeout_seconds", 120),
        "max_requests_in_trial": 1,
    }
    manifest = {
        "run_id": run_id,
        "condition_label": condition.label,
        "task_brief_sha256": sha256_bytes(canonical_json(task)),
        "condition_config_sha256": condition.config_sha256,
        "logger_version": logger_version,
        "schema_version": schema_version,
        "started_at_utc": _utc_now(),
        "model": model_record,
        "environment": environment,
        "resource_limits": resource_limits,
        "base_commit": f"experiment-spec-sha256:{experiment.spec_sha256}",
        "experiment_id": experiment.experiment_id,
        "task_id": task["id"],
        "trial": trial,
        "execution_order_index": execution_order_index,
        "randomization_seed": randomization_seed,
        "resource_hashes": [{"name": item.name, "sha256": item.sha256} for item in condition.resources],
    }
    logger = TestingLogger(run_dir, workspace, manifest)
    result: dict[str, Any] = {
        "run_id": run_id,
        "condition_label": condition.label,
        "task_id": task["id"],
        "trial": trial,
        "status": "FAILED",
        "response": None,
        "error": None,
        "run_dir": str(run_dir),
    }
    request_id = uuid.uuid4().hex
    system_prompt = _effective_system_prompt(experiment, condition)
    request_record = {
        "request_id": request_id,
        "provider": provider["type"],
        "model_id": provider["model"],
        "task_id": task["id"],
        "condition_config_sha256": condition.config_sha256,
    }
    try:
        prompt_bundle = json.dumps({"system": system_prompt, "user": task["prompt"]}, ensure_ascii=False, indent=2)
        prompt_ref = logger.capture_artifact("model-request.json", prompt_bundle, "application/json")
        logger.emit("model_request", "runner", "implementation", "observed", request_record, [prompt_ref])
        try:
            response = call_provider(provider, system_prompt, task["prompt"], condition.mock_responses.get(task["id"]))
        except ProviderError as exc:
            error_ref = logger.capture_artifact("provider-error.txt", str(exc), "text/plain; charset=utf-8")
            logger.emit("model_request_failed", "runtime", "implementation", "failed", {"request_id": request_id, "error_type": type(exc).__name__}, [error_ref])
            result["error"] = str(exc)
            raise
        response_ref = logger.capture_artifact("model-response.txt", response.text, "text/plain; charset=utf-8")
        raw_ref = logger.capture_artifact("provider-response.json", response.raw_response, "application/json")
        logger.emit(
            "model_response", "runtime", "implementation", "observed",
            {
                "request_id": request_id,
                "provider": provider["type"],
                "model_id": provider["model"],
                "provider_request_id": response.provider_request_id,
                "latency_ms": response.latency_ms,
                "finish_reason": response.finish_reason,
                "usage": response.usage,
            },
            [response_ref, raw_ref],
        )
        result.update({"status": "COMPLETED", "response": response.text, "usage": response.usage, "latency_ms": response.latency_ms})
        logger.finish("succeeded", "Model request and evidence capture completed. This is not a quality score.")
    except Exception as exc:
        if result["error"] is None:
            result["error"] = f"{type(exc).__name__}: {exc}"
        try:
            logger.finish("failed", f"Trial failed: {type(exc).__name__}")
        except Exception:
            logger.close()
    result["run_validation"] = None
    return result


def run_experiment(spec_path: str | Path, output: str | Path, qbatch_path: str | Path | None = None) -> dict[str, Any]:
    experiment = load_experiment(spec_path)
    root = Path(output).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"output must be new or empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    (root / "runs").mkdir()
    (root / "workspaces").mkdir()
    (root / "reports").mkdir()

    results: list[dict[str, Any]] = []
    total_trials = len(experiment.tasks) * experiment.trials_per_task * len(experiment.conditions)
    completed_attempts = 0
    randomization_seed = experiment.random_seed if experiment.random_seed is not None else secrets.randbits(64)
    randomizer = random.Random(randomization_seed)
    for task in experiment.tasks:
        for trial in range(1, experiment.trials_per_task + 1):
            # Randomize execution order while preserving blind A/B labels. Every
            # condition still receives its own fresh workspace and run directory.
            run_order = list(experiment.conditions)
            randomizer.shuffle(run_order)
            for order_index, condition in enumerate(run_order, start=1):
                completed_attempts += 1
                print(
                    f"[{completed_attempts}/{total_trials}] START condition={condition.label} task={task['id']} trial={trial}",
                    flush=True,
                )
                trial_result = _run_one(experiment, condition, task, trial, root, qbatch_path, order_index, randomization_seed)
                results.append(trial_result)
                print(
                    f"[{completed_attempts}/{total_trials}] {trial_result['status']} condition={condition.label} task={task['id']} trial={trial}"
                    + (f" latency_ms={trial_result.get('latency_ms')}" if trial_result.get("latency_ms") is not None else ""),
                    flush=True,
                )

    _, _, validators = load_qbatch(qbatch_path)
    validate_run, validate_pair = validators
    validation_failures: list[str] = []
    for result in results:
        try:
            result["run_validation"] = validate_run(result["run_dir"])
        except Exception as exc:
            result["run_validation"] = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
            validation_failures.append(result["run_id"])

    pair_reports: list[dict[str, Any]] = []
    grouped: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault((result["task_id"], result["trial"]), {})[result["condition_label"]] = result
    for (task_id, trial), pair in sorted(grouped.items()):
        a, b = pair.get("A"), pair.get("B")
        if not a or not b:
            pair_reports.append({"task_id": task_id, "trial": trial, "status": "FAIL", "error": "missing condition A or B"})
            continue
        try:
            checked = validate_pair(a["run_dir"], b["run_dir"], required_event_types={"run_started", "run_finished", "model_request", "model_response"})
            pair_reports.append({"task_id": task_id, "trial": trial, "status": "PASS", "verification": checked})
        except Exception as exc:
            pair_reports.append({"task_id": task_id, "trial": trial, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})

    key = {condition.label: condition.condition_id for condition in experiment.conditions}
    (root / "controller").mkdir()
    (root / "controller" / "condition-key.json").write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = {
        "report_version": "1.0",
        "classification": "EXPERIMENT_EXECUTION_AND_QBATCH_INSTRUMENTATION_VERIFICATION_ONLY",
        "experiment_id": experiment.experiment_id,
        "title": experiment.title,
        "spec_sha256": experiment.spec_sha256,
        "task_set_sha256": experiment.task_set_sha256,
        "provider": {"type": experiment.provider["type"], "model": experiment.provider["model"]},
        "trials_per_task": experiment.trials_per_task,
        "randomization_seed": randomization_seed,
        "run_count": len(results),
        "completed_trials": sum(item["status"] == "COMPLETED" for item in results),
        "failed_trials": sum(item["status"] != "COMPLETED" for item in results),
        "qbatch_validated_runs": sum(isinstance(item.get("run_validation"), dict) and item["run_validation"].get("status") != "FAIL" for item in results),
        "qbatch_pair_checks_passed": sum(item["status"] == "PASS" for item in pair_reports),
        "qbatch_pair_checks_failed": sum(item["status"] != "PASS" for item in pair_reports),
        "run_results": results,
        "pair_verification": pair_reports,
        "quality_scoring": "NOT_PERFORMED: Q-Batch verifies evidence integrity and controlled-pair instrumentation; it does not grade response quality or establish intervention efficacy.",
    }
    report["status"] = "PASS" if not validation_failures and report["failed_trials"] == 0 and report["qbatch_pair_checks_failed"] == 0 else "FAIL"
    (root / "reports" / "batch-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
