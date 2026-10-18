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
from .models import AssertionOperator, AssertionSpec, RegressionCase, RegressionResult
from .regression import RegressionEngine
from .report import render_json, render_markdown
from .runner import RUNNERS, DeterministicLocalRunner
from .storage import MAX_JSON_BYTES, PayloadTooLargeError, Repository, StorageError

DEFAULT_DB = "agentproof.db"
MAX_REPEAT = 20


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


def _repeat_count(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be an integer 1-{MAX_REPEAT}") from None
    if not 1 <= value <= MAX_REPEAT:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_REPEAT}")
    return value


def _outcome_signature(result) -> tuple:
    """What counts as 'the same result' across repeats: pass/fail per assertion, not raw output."""
    return (
        result.passed,
        result.error is not None,
        tuple((a.path, a.operator.value, a.passed) for a in result.assertions),
    )


def _run_repeated(repo: Repository, case: RegressionCase, runner_name: str, label: str, repeat: int):
    """Run ``case`` ``repeat`` times, recording every run. Returns (results, run_ids)."""
    results, run_ids = [], []
    for _ in range(repeat):
        result = RegressionEngine(RUNNERS[runner_name]()).run_case(case)
        try:
            run_ids.append(repo.record_run(case, result, label=label, runner_name=runner_name))
        except PayloadTooLargeError:
            # Runner output is untrusted: an oversized result is a failed run, not a lost one.
            result = RegressionResult(
                case_id=case.case_id,
                passed=False,
                error=f"Result exceeds {MAX_JSON_BYTES} bytes; output was not stored",
            )
            run_ids.append(repo.record_run(case, result, label=label, runner_name=runner_name))
        # Use what was actually stored (redacted), so nothing printed differs from the record.
        results.append(repo.get_run(run_ids[-1]).result)
    return results, run_ids


def _repeat_summary(results, run_ids) -> dict:
    passed = sum(1 for r in results if r.passed)
    return {
        "run_ids": run_ids,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "stable": len({_outcome_signature(r) for r in results}) == 1,
    }


def _write_report(path: str, text: str, *, force: bool) -> None:
    try:
        with open(path, "w" if force else "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        raise CliError(f"'{path}' already exists; use --force to overwrite") from None
    except OSError as exc:
        raise CliError(f"Cannot write report: {exc.strerror or exc}") from exc


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
    delete = case.add_parser("delete", help="Delete a case and all of its recorded runs.")
    delete.add_argument("case_id")
    delete.add_argument("--yes", action="store_true", help="Confirm the irreversible deletion.")

    run = sub.add_parser("run", help="Run a saved case and record the result.")
    run.add_argument("case_id")
    run.add_argument("--label", required=True)
    run.add_argument("--runner", choices=sorted(RUNNERS), default="local")
    run.add_argument(
        "--repeat",
        type=_repeat_count,
        default=1,
        help=f"Run the case N times (1-{MAX_REPEAT}) and report whether outcomes were stable.",
    )

    run_all = sub.add_parser(
        "run-all", help="Run every saved case and record each result (exit 1 if any fail)."
    )
    run_all.add_argument("--label", required=True)
    run_all.add_argument("--runner", choices=sorted(RUNNERS), default="local")
    run_all.add_argument(
        "--repeat",
        type=_repeat_count,
        default=1,
        help=f"Run each case N times (1-{MAX_REPEAT}) and report stability per case.",
    )

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
    rep.add_argument("--output", help="Write the report to this file instead of stdout.")
    rep.add_argument("--force", action="store_true", help="Overwrite --output if it exists.")
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
            elif args.case_command == "delete":
                repo.get_case(args.case_id)  # clean "not found" error before anything else
                run_count = len(repo.list_runs(args.case_id))
                if not args.yes:
                    raise CliError(
                        f"Refusing to delete '{args.case_id}' and its {run_count} recorded run(s) "
                        "without --yes"
                    )
                repo.delete_case(args.case_id)
                _emit({"deleted": args.case_id, "runs_deleted": run_count})
            else:
                _emit(repo.get_case(args.case_id).model_dump(mode="json"))
            return 0

        if args.command == "run":
            case = repo.get_case(args.case_id)
            results, run_ids = _run_repeated(repo, case, args.runner, args.label, args.repeat)
            all_passed = all(r.passed for r in results)
            if args.repeat == 1:
                _emit({"run_id": run_ids[0], "passed": results[0].passed, "error": results[0].error})
            else:
                _emit(_repeat_summary(results, run_ids))
            return 0 if all_passed else 1

        if args.command == "run-all":
            case_ids = repo.list_case_ids()
            if not case_ids:
                raise CliError("No cases saved; add one with 'case add' first")
            entries, unstable, ok_cases = [], [], 0
            for case_id in case_ids:
                case = repo.get_case(case_id)
                results, run_ids = _run_repeated(repo, case, args.runner, args.label, args.repeat)
                case_ok = all(r.passed for r in results)
                ok_cases += case_ok
                if args.repeat == 1:
                    entries.append(
                        {
                            "case_id": case_id,
                            "run_id": run_ids[0],
                            "passed": results[0].passed,
                            "error": results[0].error,
                        }
                    )
                else:
                    summary = _repeat_summary(results, run_ids)
                    if not summary["stable"]:
                        unstable.append(case_id)
                    entries.append({"case_id": case_id, **summary})
            output = {
                "total": len(entries),
                "passed": ok_cases,
                "failed": len(entries) - ok_cases,
                "results": entries,
            }
            if args.repeat > 1:
                output["unstable"] = unstable
            _emit(output)
            return 0 if ok_cases == len(entries) else 1

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
            text = render(comparison)
            if args.output:
                _write_report(args.output, text, force=args.force)
                print(f"wrote {args.output}")
            else:
                print(text, end="")
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
