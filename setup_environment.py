#!/usr/bin/env python3
"""Create a local environment and fetch pinned, read-only experiment subjects."""
from __future__ import annotations

import argparse
import subprocess
import sys
import venv
from pathlib import Path

Q_BATCH_URL = "https://github.com/memoryprismv1/q-batch-of-evidence.git"
Q_BATCH_COMMIT = "c059f5d5f969edcc7a87e7e288956a39c945cdc8"
SKILLS_URL = "https://github.com/memoryprismv1/cognitive-interface-ai-skills.git"
SKILLS_COMMIT = "fc530b6815eead24aa8655cbbb4bfe0dd8c9f666"
ROOT = Path(__file__).resolve().parent


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def prepare_checkout(url: str, commit: str, target: Path, label: str) -> None:
    if target.exists():
        if not (target / ".git").exists():
            raise SystemExit(f"Refusing to replace non-Git directory: {target}")
        status = subprocess.run(["git", "status", "--porcelain"], cwd=target, check=True,
                                capture_output=True, text=True).stdout.strip()
        if status:
            raise SystemExit(f"{label} checkout has local changes; refusing to overwrite it: {target}")
        current = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target, check=True,
                                 capture_output=True, text=True).stdout.strip()
        if current != commit:
            run(["git", "fetch", "origin", "main"], cwd=target)
            run(["git", "checkout", "--detach", commit], cwd=target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", url, str(target)])
        run(["git", "checkout", "--detach", commit], cwd=target)
    actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target, check=True,
                            capture_output=True, text=True).stdout.strip()
    if actual != commit:
        raise SystemExit(f"{label} checkout revision mismatch: expected {commit}, got {actual}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", default=".venv", help="virtual-environment directory")
    parser.add_argument("--qbatch-dir", default=".vendor/q-batch-of-evidence", help="Q-Batch checkout")
    parser.add_argument("--skills-dir", default=".vendor/cognitive-interface-ai-skills", help="read-only skills checkout")
    args = parser.parse_args()
    venv_path = (ROOT / args.venv).resolve()
    qbatch_path = (ROOT / args.qbatch_dir).resolve()
    skills_path = (ROOT / args.skills_dir).resolve()
    prepare_checkout(Q_BATCH_URL, Q_BATCH_COMMIT, qbatch_path, "Q-Batch")
    prepare_checkout(SKILLS_URL, SKILLS_COMMIT, skills_path, "Cognitive skills")
    if not venv_path.exists():
        venv.EnvBuilder(with_pip=True).create(venv_path)
    python = venv_path / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        raise SystemExit(f"Virtual environment is missing its Python executable: {python}")
    run([str(python), "-m", "pip", "install", "--editable", str(ROOT)])
    print("Environment ready")
    print(f"Python: {python}")
    print(f"Q-Batch: {qbatch_path} @ {Q_BATCH_COMMIT}")
    print(f"Cognitive skills (read-only): {skills_path} @ {SKILLS_COMMIT}")
    print("Next: aier --help; real-model runs require AI_RUNTIME_API_KEY.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
