"""Thin bridge to the separately maintained Q-Batch implementation.

No Q-Batch implementation is copied into this repository. The runtime imports
its logger and validator from a pinned external checkout.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


class QBatchUnavailable(RuntimeError):
    pass


def qbatch_root(explicit: str | Path | None = None) -> Path:
    candidate = explicit or os.environ.get("Q_BATCH_PATH")
    if candidate is None:
        candidate = Path(__file__).resolve().parents[2] / ".vendor" / "q-batch-of-evidence"
    root = Path(candidate).expanduser().resolve()
    if not (root / "testing_logger" / "logger.py").is_file() or not (root / "experiments" / "ct_ab" / "validate_log.py").is_file():
        raise QBatchUnavailable("Q-Batch checkout not found. Run `python setup_environment.py` or set Q_BATCH_PATH to a Q-Batch repository checkout.")
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
    return root


def load_qbatch(explicit: str | Path | None = None) -> tuple[Any, Any, Any]:
    qbatch_root(explicit)
    try:
        from testing_logger.logger import TestingLogger, LOGGER_VERSION, SCHEMA_VERSION, utc_now
        from experiments.ct_ab.validate_log import validate_run, validate_pair
    except ImportError as exc:
        raise QBatchUnavailable(f"Could not import the pinned Q-Batch verifier: {exc}") from exc
    return TestingLogger, (LOGGER_VERSION, SCHEMA_VERSION, utc_now), (validate_run, validate_pair)
