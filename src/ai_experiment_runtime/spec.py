"""Load and validate the portable JSON experiment format."""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import canonical_json, sha256_bytes, sha256_file, sha256_text

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class SpecError(ValueError):
    """Raised when an experiment definition is ambiguous or malformed."""


@dataclass(frozen=True)
class Resource:
    name: str
    path: str
    content: str
    sha256: str


@dataclass(frozen=True)
class LoadedCondition:
    condition_id: str
    label: str
    system_instruction: str
    resources: tuple[Resource, ...]
    mock_responses: dict[str, str]
    config_sha256: str


@dataclass(frozen=True)
class LoadedExperiment:
    path: Path
    raw: dict[str, Any]
    experiment_id: str
    title: str
    provider: dict[str, Any]
    tasks: tuple[dict[str, str], ...]
    conditions: tuple[LoadedCondition, ...]
    trials_per_task: int
    base_system_prompt: str
    spec_sha256: str
    task_set_sha256: str
    random_seed: int | None


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise SpecError(f"{field} must match {ID_RE.pattern}")
    return value


def load_experiment(path: str | Path) -> LoadedExperiment:
    spec_path = Path(path).expanduser().resolve(strict=True)
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"cannot read experiment JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecError("experiment definition must be a JSON object")
    if raw.get("schema_version") != "1.0":
        raise SpecError("schema_version must be '1.0'")
    experiment_id = _require_id(raw.get("experiment_id"), "experiment_id")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise SpecError("title must be a non-empty string")

    provider = raw.get("provider")
    if not isinstance(provider, dict) or provider.get("type") not in {"mock", "openai-compatible"}:
        raise SpecError("provider.type must be 'mock' or 'openai-compatible'")
    if not isinstance(provider.get("model"), str) or not provider["model"].strip():
        raise SpecError("provider.model must be a non-empty string")
    timeout = provider.get("timeout_seconds", 120)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
        raise SpecError("provider.timeout_seconds must be between 1 and 3600")
    if provider["type"] == "openai-compatible":
        base_url = provider.get("base_url", "https://api.openai.com/v1")
        if not isinstance(base_url, str):
            raise SpecError("base_url must be a URL")
        parsed_url = urlsplit(base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if not parsed_url.netloc or not parsed_url.hostname or parsed_url.username or parsed_url.password:
            raise SpecError("base_url must have a host and must not contain embedded credentials")
        if parsed_url.scheme != "https" and not (parsed_url.scheme == "http" and parsed_url.hostname in local_hosts):
            raise SpecError("base_url must use HTTPS, except for a localhost HTTP endpoint")
        if parsed_url.query or parsed_url.fragment:
            raise SpecError("base_url must not contain query strings or fragments")
        provider = dict(provider)
        provider["base_url"] = base_url.rstrip("/")
        api_key_env = provider.get("api_key_env", "AI_RUNTIME_API_KEY")
        if not isinstance(api_key_env, str) or not api_key_env.isidentifier():
            raise SpecError("provider.api_key_env must be an environment-variable name")
        provider["api_key_env"] = api_key_env

    tasks_raw = raw.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise SpecError("tasks must be a non-empty array")
    tasks: list[dict[str, str]] = []
    seen_tasks: set[str] = set()
    for index, task in enumerate(tasks_raw):
        if not isinstance(task, dict):
            raise SpecError(f"tasks[{index}] must be an object")
        task_id = _require_id(task.get("id"), f"tasks[{index}].id")
        prompt = task.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise SpecError(f"tasks[{index}].prompt must be a non-empty string")
        if task_id in seen_tasks:
            raise SpecError(f"duplicate task id: {task_id}")
        seen_tasks.add(task_id)
        tasks.append({"id": task_id, "prompt": prompt})

    conditions_raw = raw.get("conditions")
    if not isinstance(conditions_raw, list) or len(conditions_raw) != 2:
        raise SpecError("conditions must contain exactly two independent conditions for the initial paired runner")
    conditions: list[LoadedCondition] = []
    seen_condition_ids: set[str] = set()
    seen_labels: set[str] = set()
    for index, condition in enumerate(conditions_raw):
        if not isinstance(condition, dict):
            raise SpecError(f"conditions[{index}] must be an object")
        condition_id = _require_id(condition.get("id"), f"conditions[{index}].id")
        label = condition.get("label")
        if label not in {"A", "B"}:
            raise SpecError("condition.label must be 'A' or 'B'")
        if condition_id in seen_condition_ids or label in seen_labels:
            raise SpecError("condition ids and labels must be unique")
        seen_condition_ids.add(condition_id)
        seen_labels.add(label)
        instruction = condition.get("system_instruction", "")
        if not isinstance(instruction, str):
            raise SpecError(f"conditions[{index}].system_instruction must be text")
        resources_raw = condition.get("resources", [])
        if not isinstance(resources_raw, list):
            raise SpecError(f"conditions[{index}].resources must be an array")
        resources: list[Resource] = []
        for resource_index, resource in enumerate(resources_raw):
            if not isinstance(resource, dict) or not isinstance(resource.get("name"), str) or not isinstance(resource.get("path"), str):
                raise SpecError(f"conditions[{index}].resources[{resource_index}] needs name and path")
            resource_path = (spec_path.parent / resource["path"]).resolve(strict=True)
            if not resource_path.is_file():
                raise SpecError(f"resource is not a file: {resource_path}")
            try:
                content = resource_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise SpecError(f"resource must be readable UTF-8 text: {resource_path}: {exc}") from exc
            resources.append(Resource(resource["name"], resource["path"], content, sha256_file(resource_path)))
        mock_responses = condition.get("mock_responses", {})
        if not isinstance(mock_responses, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in mock_responses.items()):
            raise SpecError(f"conditions[{index}].mock_responses must map task IDs to response text")
        condition_fingerprint = {
            "system_instruction": instruction,
            "resources": [{"name": r.name, "path": r.path, "sha256": r.sha256} for r in resources],
            "mock_responses": mock_responses,
        }
        conditions.append(LoadedCondition(condition_id, label, instruction, tuple(resources), dict(mock_responses), sha256_bytes(canonical_json(condition_fingerprint))))
    if seen_labels != {"A", "B"}:
        raise SpecError("the two conditions must be labelled A and B")

    random_seed = raw.get("random_seed")
    if random_seed is not None and (not isinstance(random_seed, int) or isinstance(random_seed, bool) or not 0 <= random_seed < 2**64):
        raise SpecError("random_seed must be an integer between 0 and 2**64-1")

    trials = raw.get("trials_per_task", 1)
    if not isinstance(trials, int) or isinstance(trials, bool) or not 1 <= trials <= 100:
        raise SpecError("trials_per_task must be an integer from 1 to 100")
    base_system_prompt = raw.get("system_prompt", "You are participating in a controlled AI experiment. Follow the instructions and answer the task.")
    if not isinstance(base_system_prompt, str):
        raise SpecError("system_prompt must be text")

    spec_sha = sha256_bytes(canonical_json(raw))
    task_set_sha = sha256_bytes(canonical_json(tasks))
    return LoadedExperiment(spec_path, raw, experiment_id, title, dict(provider), tuple(tasks), tuple(conditions), trials, base_system_prompt, spec_sha, task_set_sha, random_seed)
