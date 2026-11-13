"""Command-line interface for the AI Experiment Runtime."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluator import EvaluationError, evaluate_report
from .qbatch import QBatchUnavailable, load_qbatch
from .runner import run_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aier", description="Run controlled AI experiments and verify their evidence with Q-Batch.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a two-condition experiment from a JSON spec")
    run.add_argument("--spec", required=True, help="path to an experiment JSON file")
    run.add_argument("--output", required=True, help="new or empty output directory")
    run.add_argument("--qbatch-path", help="path to a pinned Q-Batch checkout")
    evaluate = sub.add_parser("evaluate", help="summarize external blinded scores against a predeclared rubric")
    evaluate.add_argument("--report", required=True, help="batch-report.json from a completed run")
    evaluate.add_argument("--rubric", required=True, help="predeclared rubric JSON")
    evaluate.add_argument("--scores", required=True, help="external score sheet JSON")
    evaluate.add_argument("--output", required=True, help="evaluation report JSON path")
    verify = sub.add_parser("verify", help="verify an existing Q-Batch run directory")
    verify.add_argument("--run-dir", required=True)
    verify.add_argument("--qbatch-path", help="path to a pinned Q-Batch checkout")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            report = run_experiment(args.spec, args.output, args.qbatch_path)
            print(json.dumps({k: v for k, v in report.items() if k != "run_results"}, indent=2, sort_keys=True))
            return 0 if report["status"] == "PASS" else 1
        if args.command == "evaluate":\n            result = evaluate_report(args.report, args.rubric, args.scores)\n            output = Path(args.output)\n            output.parent.mkdir(parents=True, exist_ok=True)\n            output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\\n", encoding="utf-8")\n            print(json.dumps(result, indent=2, sort_keys=True))\n            return 0\n        _, _, validators = load_qbatch(args.qbatch_path)
        validation = validators[0](Path(args.run_dir))
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, QBatchUnavailable, EvaluationError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
