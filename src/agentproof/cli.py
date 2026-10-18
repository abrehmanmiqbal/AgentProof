"""Command-line entry point for AgentProof.

Imported case files are untrusted data: they are size-capped, parsed as JSON only, and
validated through typed models. Nothing in a case file is ever executed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .comparison import Verdict, compare_runs
from .models import AssertionOperator, AssertionSpec, RegressionCase
from .regression import RegressionEngine
from .report import render_json, render_markdown
from .runner import RUNNERS, DeterministicLocalRunner
from .storage import MAX_JSON_BYTES, Repository, StorageError

DEFAULT_DB = "agentproof.db"


class CliError(Exception):
    pass


def _emit(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=False))


def load_case_file(path: str) -> RegressionCase:
    file = Path(path)
    try:
        with file.open("rb") as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
    except OSError as exc:
        raise CliError(f"Cannot read case file: {exc.strerror or exc}") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise CliError(f"Case file exceeds {MAX_JSON_BYTES} bytes")
    try:
        return RegressionCase.model_validate_json(raw)
    except ValidationError as exc:
        raise CliError(f"Invalid case file: {exc.error_count()} validation error(s): {exc}") from exc


def _demo() -> int:
    case = RegressionCase(
        case_id="demo-greeting",
        name="Deterministic greeting",
        input={"action": "greet", "name": "AgentProof"},
        assertions=[
            AssertionSpec(
                path="message", operator=AssertionOperator.EQUALS, expected="Hello, AgentProof!"
            ),
            AssertionSpec(path="action", operator=AssertionOperator.EQUALS, expected="greet"),
        ],
    )
    result = RegressionEngine(DeterministicLocalRunner()).run_case(case)
    _emit(result.model_dump(mode="json"))
    return 0 if result.passed else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentproof", description="Offline-first AI agent regression testing.")
    parser.add_argument("--db", default=os.environ.get("AGENTPROOF_DB", DEFAULT_DB), help="SQLite file")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="Run the built-in offline demo case.")

    case = sub.add_parser("case", help="Manage saved regression cases.").add_subparsers(
        dest="case_command", required=True
    )
    add = case.add_parser("add", help="Import a case from a JSON file.")
    add.add_argument("file")
    add.add_argument("--overwrite", action="store_true")
    case.add_parser("list", help="List case ids.")
    show = case.add_parser("show", help="Show a saved case.")
    show.add_argument("case_id")

    run = sub.add_parser("run", help="Run a saved case and record the result.")
    run.add_argument("case_id")
    run.add_argument("--label", required=True)
    run.add_argument("--runner", choices=sorted(RUNNERS), default="local")

    runs = sub.add_parser("runs", help="List recorded runs for a case.")
    runs.add_argument("case_id")

    cmp = sub.add_parser("compare", help="Compare two recorded runs (exit 1 if regressed).")
    cmp.add_argument("before_run_id", type=int)
    cmp.add_argument("after_run_id", type=int)

    rep = sub.add_parser(
        "report", help="Render a deterministic report comparing two runs (exit 1 if regressed)."
    )
    rep.add_argument("before_run_id", type=int)
    rep.add_argument("after_run_id", type=int)
    rep.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "demo":
        return _demo()

    with Repository(args.db) as repo:
        if args.command == "case":
            if args.case_command == "add":
                digest = repo.save_case(load_case_file(args.file), overwrite=args.overwrite)
                _emit({"saved": True, "case_hash": digest})
            elif args.case_command == "list":
                _emit(repo.list_case_ids())
            else:
                _emit(repo.get_case(args.case_id).model_dump(mode="json"))
            return 0

        if args.command == "run":
            case = repo.get_case(args.case_id)
            result = RegressionEngine(RUNNERS[args.runner]()).run_case(case)
            run_id = repo.record_run(case, result, label=args.label, runner_name=args.runner)
            _emit({"run_id": run_id, "passed": result.passed, "error": result.error})
            return 0 if result.passed else 1

        if args.command == "runs":
            _emit(
                [
                    {
                        "run_id": r.run_id,
                        "label": r.label,
                        "runner": r.runner_name,
                        "passed": r.result.passed,
                        "created_at": r.created_at,
                    }
                    for r in repo.list_runs(args.case_id)
                ]
            )
            return 0

        if args.command == "compare":
            comparison = compare_runs(repo.get_run(args.before_run_id), repo.get_run(args.after_run_id))
            _emit(comparison.model_dump(mode="json"))
            return 1 if comparison.verdict == Verdict.REGRESSED else 0

        if args.command == "report":
            comparison = compare_runs(repo.get_run(args.before_run_id), repo.get_run(args.after_run_id))
            render = render_json if args.format == "json" else render_markdown
            print(render(comparison), end="")
            return 1 if comparison.verdict == Verdict.REGRESSED else 0

    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (StorageError, CliError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
