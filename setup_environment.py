#!/usr/bin/env python3
"""Create a local virtual environment and fetch the pinned Q-Batch verifier."""
from __future__ import annotations

import argparse
import subprocess
import sys
import venv
from pathlib import Path

Q_BATCH_URL = "https://github.com/memoryprismv1/q-batch-of-evidence.git"
Q_BATCH_COMMIT = "c059f5d5f969edcc7a87e7e288956a39c945cdc8"
ROOT = Path(__file__).resolve().parent


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", default=".venv", help="virtual-environment directory (default: .venv)")
    parser.add_argument("--qbatch-dir", default=".vendor/q-batch-of-evidence", help="Q-Batch checkout directory")
    args = parser.parse_args()
    venv_path = (ROOT / args.venv).resolve()
    qbatch_path = (ROOT / args.qbatch_dir).resolve()
    if qbatch_path.exists():
        if not (qbatch_path / ".git").exists():
            raise SystemExit(f"Refusing to replace non-Git directory: {qbatch_path}")
        status = subprocess.run(["git", "status", "--porcelain"], cwd=qbatch_path, check=True, capture_output=True, text=True)
        if status.stdout.strip():
            raise SystemExit(f"Q-Batch checkout has local changes; refusing to overwrite it: {qbatch_path}")
        current = subprocess.run(["git", "rev-parse", "HEAD"], cwd=qbatch_path, check=True, capture_output=True, text=True).stdout.strip()
        if current != Q_BATCH_COMMIT:
            run(["git", "fetch", "origin", Q_BATCH_COMMIT], cwd=qbatch_path)
            run(["git", "checkout", "--detach", Q_BATCH_COMMIT], cwd=qbatch_path)
    else:
        qbatch_path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", Q_BATCH_URL, str(qbatch_path)])
        run(["git", "checkout", "--detach", Q_BATCH_COMMIT], cwd=qbatch_path)
    if not venv_path.exists():
        venv.EnvBuilder(with_pip=True).create(venv_path)
    python = venv_path / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    run([str(python), "-m", "pip", "install", "--editable", str(ROOT)])
    print("Environment ready")
    print(f"Python: {python}")
    print(f"Q-Batch: {qbatch_path} @ {Q_BATCH_COMMIT}")
    print("Next: run `aier --help`. Q_BATCH_PATH is optional when using this default checkout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
