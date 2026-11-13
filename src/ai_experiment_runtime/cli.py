"""Command-line interface for the AI Experiment Runtime."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .blinding import BlindingError, export_blinded_packet
from .evaluator import EvaluationError, evaluate_report
from .qbatch import QBatchUnavailable, load_qbatch
from .runner import run_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aier", description="Run controlled AI experiments and verify their evidence with Q-Batch.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a two-condition experiment from a JSON spec")
    run.add_argument("--spec", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--qbatch-path")
    blind = sub.add_parser("blind-export", help="export responses for scoring without revealing condition identity")
    blind.add_argument("--report", required=True)
    blind.add_argument("--spec", required=True)
    blind.add_argument("--packet", required=True)
    blind.add_argument("--private-key", required=True, help="controller-only key; never give this file to the scorer")
    evaluate = sub.add_parser("evaluate", help="resolve blinded scores and calculate paired descriptive differences")
    evaluate.add_argument("--report", required=True)
    evaluate.add_argument("--rubric", required=True)
    evaluate.add_argument("--scores", required=True)
    evaluate.add_argument("--private-key", required=True)
    evaluate.add_argument("--output", required=True)
    verify = sub.add_parser("verify", help="verify an existing Q-Batch run directory")
    verify.add_argument("--run-dir", required=True)
    verify.add_argument("--qbatch-path")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            report = run_experiment(args.spec, args.output, args.qbatch_path)
            print(json.dumps({k: v for k, v in report.items() if k != "run_results"}, indent=2, sort_keys=True))
            return 0 if report["status"] == "PASS" else 1
        if args.command == "blind-export":
            result = export_blinded_packet(args.report, args.spec, args.packet, args.private_key)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "evaluate":
            result = evaluate_report(args.report, args.rubric, args.scores, args.private_key)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        _, _, validators = load_qbatch(args.qbatch_path)
        validation = validators[0](Path(args.run_dir))
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, QBatchUnavailable, EvaluationError, BlindingError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
