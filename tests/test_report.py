import json
from pathlib import Path

from agentproof.cli import main
from agentproof.comparison import (
    AssertionChange,
    AssertionDiff,
    Comparison,
    Verdict,
)
from agentproof.models import AssertionOperator
from agentproof.report import render_json, render_markdown

GOLDEN = Path(__file__).parent / "golden" / "report_improved.md"


def _diff(path, change, before=None, after=None, op=AssertionOperator.EQUALS):
    return AssertionDiff(
        path=path, operator=op, change=change, before_actual=before, after_actual=after
    )


def _improved() -> Comparison:
    return Comparison(
        case_id="greet-ava",
        before_run_id=1,
        after_run_id=2,
        same_case_definition=True,
        verdict=Verdict.IMPROVED,
        diffs=[
            _diff("action", AssertionChange.STILL_PASSING, "greet", "greet"),
            _diff("message", AssertionChange.FIXED, "Hi Ava", "Hello, Ava!"),
        ],
    )


def test_markdown_matches_golden_file():
    assert render_markdown(_improved()) == GOLDEN.read_text()


def test_markdown_is_deterministic_and_has_no_timestamps():
    first, second = render_markdown(_improved()), render_markdown(_improved())
    assert first == second
    assert "created_at" not in first and "T00:" not in first


def test_untrusted_values_cannot_break_table_or_inject_markdown():
    hostile = "a|b\n| x | y |\n`<script>`[link](http://evil)"
    c = Comparison(
        case_id="bad|id",
        verdict=Verdict.REGRESSED,
        diffs=[_diff("p|q", AssertionChange.REGRESSED, "ok", hostile)],
    )
    out = render_markdown(c)
    rows = [ln for ln in out.splitlines() if ln.startswith("| ") and "---" not in ln]
    assert len(rows) == 2  # header + exactly one data row, no injected rows
    assert "<script>" not in out
    assert "](http" not in out


def test_long_values_are_truncated():
    c = Comparison(
        case_id="c",
        verdict=Verdict.UNCHANGED,
        diffs=[_diff("p", AssertionChange.STILL_PASSING, "x" * 5000, "x" * 5000)],
    )
    out = render_markdown(c)
    assert len(out) < 1500
    assert "…" in out


def test_added_and_removed_show_dash_not_null():
    c = Comparison(
        case_id="c",
        verdict=Verdict.UNCHANGED,
        diffs=[
            _diff("new", AssertionChange.ADDED, None, 1),
            _diff("old", AssertionChange.REMOVED, 2, None),
        ],
    )
    out = render_markdown(c)
    assert "| added | — | 1 |" in out
    assert "| removed | 2 | — |" in out


def test_run_errors_are_reported_collapsed_and_truncated():
    c = Comparison(
        case_id="c",
        verdict=Verdict.REGRESSED,
        after_error="boom\nsecond line " + "y" * 2000,
        diffs=[],
    )
    out = render_markdown(c)
    assert "## Run errors" in out
    assert "boom second line" in out
    assert len(out) < 1200


def test_json_report_is_stable_sorted_and_round_trips():
    out = render_json(_improved())
    assert out == render_json(_improved())
    assert out.endswith("\n")
    data = json.loads(out)
    assert data["verdict"] == "improved"
    assert list(data) == sorted(data)


def _setup(tmp_path):
    case = {
        "case_id": "greet-ava",
        "name": "Greet Ava",
        "input": {"action": "greet", "name": "Ava"},
        "assertions": [
            {"path": "message", "operator": "equals", "expected": "Hello, Ava!"},
            {"path": "action", "operator": "equals", "expected": "greet"},
        ],
    }
    f = tmp_path / "case.json"
    f.write_text(json.dumps(case))
    db = ["--db", str(tmp_path / "t.db")]
    assert main([*db, "case", "add", str(f)]) == 0
    assert main([*db, "run", "greet-ava", "--label", "before", "--runner", "local-legacy"]) == 1
    assert main([*db, "run", "greet-ava", "--label", "after", "--runner", "local"]) == 0
    return db


def test_cli_report_markdown_default(tmp_path, capsys):
    db = _setup(tmp_path)
    capsys.readouterr()
    assert main([*db, "report", "1", "2"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# AgentProof report: greet-ava")
    assert "Verdict: **IMPROVED**" in out


def test_cli_report_json_format(tmp_path, capsys):
    db = _setup(tmp_path)
    capsys.readouterr()
    assert main([*db, "report", "1", "2", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "improved"


def test_cli_report_exits_nonzero_when_regressed(tmp_path, capsys):
    db = _setup(tmp_path)
    capsys.readouterr()
    assert main([*db, "report", "2", "1"]) == 1


def test_cli_report_unknown_run_is_clean_error(tmp_path, capsys):
    db = _setup(tmp_path)
    capsys.readouterr()
    assert main([*db, "report", "1", "99"]) == 2
    assert "error:" in capsys.readouterr().err
