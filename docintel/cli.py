import argparse
import json
import sys
from pathlib import Path

from .evaluate import evaluate
from .pipeline import atomic_json, run
from .providers import Baseline, OpenAI, ProviderError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence Ledger invoice extraction")
    sub = parser.add_subparsers(dest="command", required=True)
    batch = sub.add_parser("run", help="Process or resume a directory of UTF-8 invoices")
    batch.add_argument("--input", default="data/invoices")
    batch.add_argument("--db", default="runs/checkpoints.sqlite")
    batch.add_argument("--output", default="runs/report.json")
    batch.add_argument("--retry-failed", action="store_true")
    batch.add_argument("--stop-after", type=int)
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--dataset", default="data")
    evaluation.add_argument("--output", default="runs/evaluation.json")
    for command in (batch, evaluation):
        command.add_argument("--provider", choices=["baseline", "openai"], default="baseline")
        command.add_argument("--model", help="Required for openai; choose a structured-output compatible model")
    serve = sub.add_parser("serve", help="Local offline demo and batch-report viewer")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--report", default="runs/report.json")
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve as start
            start(args.port, Path(args.report))
            return 0
        if args.provider == "openai" and not args.model:
            raise ValueError("--model is required for openai mode")
        provider = Baseline() if args.provider == "baseline" else OpenAI(args.model)
        if args.command == "run":
            report = run(args.input, args.db, args.output, provider, args.retry_failed, args.stop_after)
            failed = sum(x["status"] == "failed" for x in report["documents"])
            print(json.dumps({"processed": report["processed"], "skipped": report["skipped"],
                              "failed": failed, "remaining": report["remaining"], "report": args.output}))
            return 2 if failed else 0
        report = evaluate(args.dataset, provider)
        atomic_json(args.output, report)
        print(json.dumps({key: report[key] for key in ("documents", "field_exact_match", "decision_accuracy", "unsafe_validations", "extraction_failures")}))
        return 0 if (report["field_exact_match"] == 1 and report["decision_accuracy"] == 1 and not report["extraction_failures"]) else 2
    except (ValueError, OSError, ProviderError, RuntimeError):
        # Do not print exception strings: filesystem paths or provider payloads may be sensitive.
        print("Operation failed. Check input, configuration, permissions, and checkpoint ownership.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
