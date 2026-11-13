"""Model-provider adapters. Credentials are read from environment variables only."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ModelResponse:
    text: str
    usage: dict[str, Any]
    finish_reason: str | None
    provider_request_id: str | None
    raw_response: str
    latency_ms: float


class ProviderError(RuntimeError):
    """A model-provider request failed or returned an unsupported response."""


def call_provider(config: Mapping[str, Any], system_prompt: str, user_prompt: str, mock_response: str | None = None) -> ModelResponse:
    provider_type = config["type"]
    if provider_type == "mock":
        if mock_response is None:
            mock_response = "MOCK RESPONSE: " + user_prompt[:240]
        raw = json.dumps({"mock": True, "model": config["model"], "response": mock_response}, ensure_ascii=False)
        return ModelResponse(mock_response, {"mock": True}, "stop", "mock-fixture", raw, 0.0)
    if provider_type != "openai-compatible":
        raise ProviderError(f"unsupported provider type: {provider_type}")

    base_url = str(config.get("base_url", "https://api.openai.com/v1")).rstrip("/")
    endpoint = base_url + "/chat/completions"
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config.get("temperature", 0),
        "max_tokens": config.get("max_tokens", 1200),
    }
    headers = {"Content-Type": "application/json"}
    key_name = str(config.get("api_key_env", "AI_RUNTIME_API_KEY"))
    api_key = os.environ.get(key_name)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=float(config.get("timeout_seconds", 120))) as response:
            raw_bytes = response.read()
            provider_request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    except urllib.error.HTTPError as exc:
        # Do not echo provider response bodies; they may include private prompt data.
        raise ProviderError(f"provider returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"provider transport failed: {type(exc).__name__}") from exc
    latency = round((time.monotonic() - started) * 1000, 3)
    try:
        raw_text = raw_bytes.decode("utf-8")
        doc = json.loads(raw_text)
        choices = doc["choices"]
        message = choices[0]["message"]
        content = message.get("content")
        if not isinstance(content, str):
            raise TypeError("message.content is not a string")
        usage = doc.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        finish_reason = choices[0].get("finish_reason")
        return ModelResponse(content, usage, finish_reason, provider_request_id, raw_text, latency)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ProviderError(f"provider response did not match the supported chat-completions shape: {type(exc).__name__}") from exc
