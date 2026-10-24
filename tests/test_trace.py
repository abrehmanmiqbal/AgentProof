"""Trace -> regression case conversion. A trace is untrusted DATA (D-004): it is parsed with
strict JSON, bounded, redacted-checked, and never executed."""
import json

import pytest

from regressagent.assertions import evaluate_assertion
from regressagent.cli import load_case_file, main
from regressagent.models import MAX_ASSERTIONS
from regressagent.runner import DeterministicLocalRunner
from regressagent.trace import TraceError, case_from_trace, parse_trace

GITHUB_TOKEN = "github_pat_" + "A1b2C3d4E5" * 3  # fake, but matches the token pattern


def trace(output=None, input_=None, trace_id="t1", **extra):
    data = {
        "trace_id": trace_id,
        "input": {"q": "hi"} if input_ is None else input_,
        "output": {"a": 1} if output is None else output,
    }
    data.update(extra)
    return json.dumps(data).encode()


def passes_on_original(case, output):
    return all(evaluate_assertion(output, spec).passed for spec in case.assertions)


# ---------------------------------------------------------------- parsing
def test_parse_valid_trace():
    t = parse_trace(trace())
    assert t.trace_id == "t1" and t.input == {"q": "hi"} and t.output == {"a": 1}


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"\xff\xfe",
        b"[]",
        b'{"trace_id": "t", "input": {}}',  # missing output
        b'{"trace_id": "t", "input": [], "output": {}}',  # input not an object
        b'{"trace_id": "t", "input": {}, "output": []}',  # output not an object
        b'{"trace_id": "", "input": {}, "output": {}}',
        b'{"trace_id": "' + b"x" * 129 + b'", "input": {}, "output": {}}',
        b'{"trace_id": "t", "input": {}, "output": {"n": NaN}}',
        b'{"trace_id": "t", "input": {}, "output": {"n": Infinity}}',
        trace(surprise=1),  # unknown top-level field
    ],
)
def test_malformed_traces_are_rejected_cleanly(raw):
    with pytest.raises(TraceError):
        parse_trace(raw)


def test_deeply_nested_trace_is_rejected():
    deep: object = 1
    for _ in range(40):
        deep = {"k": deep}
    with pytest.raises(TraceError, match="nested"):
        parse_trace(trace(output={"deep": deep}))


# ---------------------------------------------------------------- generation
def test_default_generates_equals_for_every_scalar_leaf_and_round_trips():
    output = {
        "message": "Hello",
        "count": 3,
        "ratio": 0.5,
        "ok": True,
        "nothing": None,
        "nested": {"a": "x", "list": [10, {"b": "y"}]},
    }
    case, notes = case_from_trace(parse_trace(trace(output=output)))
    paths = [a.path for a in case.assertions]
    assert paths == [
        "message", "count", "ratio", "ok", "nothing", "nested.a", "nested.list.0", "nested.list.1.b",
    ]  # fmt: skip
    assert all(a.operator.value == "equals" for a in case.assertions)
    assert passes_on_original(case, output)
    assert notes == []


def test_bool_and_int_stay_distinct():
    case, _ = case_from_trace(parse_trace(trace(output={"flag": True, "one": 1})))
    assert not evaluate_assertion({"flag": 1, "one": 1}, case.assertions[0]).passed


def test_defaults_and_overrides_for_case_id_and_name():
    t = parse_trace(trace(trace_id="run-42"))
    case, _ = case_from_trace(t)
    assert case.case_id == "run-42" and "run-42" in case.name
    case, _ = case_from_trace(t, case_id="mine", name="My case")
    assert (case.case_id, case.name) == ("mine", "My case")
    assert case.input == {"q": "hi"}


def test_unaddressable_keys_are_skipped_with_a_note():
    output = {"a.b": 1, "": 2, "fine": 3}
    case, notes = case_from_trace(parse_trace(trace(output=output)))
    assert [a.path for a in case.assertions] == ["fine"]
    assert len(notes) == 2 and all("skipped" in n for n in notes)


def test_very_long_paths_are_skipped():
    output = {"k" * 600: 1, "nested": {"j" * 600: 2}, "ok": 3}
    case, notes = case_from_trace(parse_trace(trace(output=output)))
    assert [a.path for a in case.assertions] == ["ok"]
    assert sum("path longer" in n for n in notes) == 2
    assert all(len(n) < 200 for n in notes)  # notes never echo the huge path


def test_long_strings_are_skipped():
    case, notes = case_from_trace(parse_trace(trace(output={"big": "x" * 1001, "ok": "y"})))
    assert [a.path for a in case.assertions] == ["ok"]
    assert any("big" in n and "long" in n for n in notes)


def test_secret_looking_values_are_skipped_and_never_echoed():
    output = {"api_key": "sk-live-abcdef1234567890", "msg": f"token {GITHUB_TOKEN}", "ok": "fine"}
    case, notes = case_from_trace(parse_trace(trace(output=output)))
    assert [a.path for a in case.assertions] == ["ok"]
    joined = " ".join(notes) + json.dumps(case.model_dump())
    assert GITHUB_TOKEN not in joined and "sk-live-abcdef1234567890" not in joined
    assert any("api_key" in n for n in notes) and any("msg" in n for n in notes)


def test_secret_in_input_is_refused():
    with pytest.raises(TraceError, match="input"):
        case_from_trace(parse_trace(trace(input_={"password": "hunter2hunter2"})))
    with pytest.raises(TraceError, match="input"):
        case_from_trace(parse_trace(trace(input_={"q": f"use {GITHUB_TOKEN}"})))


def test_too_many_leaves_asks_for_explicit_paths():
    many = {f"k{i}": i for i in range(MAX_ASSERTIONS + 1)}
    with pytest.raises(TraceError, match="--path"):
        case_from_trace(parse_trace(trace(output=many)))
    exact = {f"k{i}": i for i in range(MAX_ASSERTIONS)}
    case, _ = case_from_trace(parse_trace(trace(output=exact)))
    assert len(case.assertions) == MAX_ASSERTIONS


def test_nothing_assertable_is_an_error():
    with pytest.raises(TraceError, match="no assertable"):
        case_from_trace(parse_trace(trace(output={"a.b": 1})))
    with pytest.raises(TraceError, match="no assertable"):
        case_from_trace(parse_trace(trace(output={})))


def test_explicit_paths_select_and_allow_composites():
    output = {"a": 1, "b": {"c": [1, 2]}, "d": "x"}
    case, _ = case_from_trace(parse_trace(trace(output=output)), paths=["b.c", "a", "a"])
    assert [(s.path, s.expected) for s in case.assertions] == [("b.c", [1, 2]), ("a", 1)]
    assert passes_on_original(case, output)


def test_explicit_path_errors():
    t = parse_trace(trace(output={"a": 1, "api_key": "sk-live-abcdef1234567890"}))
    with pytest.raises(TraceError, match="nope"):
        case_from_trace(t, paths=["nope"])
    with pytest.raises(TraceError, match="secret") as exc:
        case_from_trace(t, paths=["api_key"])
    assert "sk-live-abcdef1234567890" not in str(exc.value)
    with pytest.raises(TraceError, match="at most"):
        case_from_trace(t, paths=[f"p{i}" for i in range(MAX_ASSERTIONS + 1)])


# ---------------------------------------------------------------- CLI
def cli(tmp_path, *argv):
    return main(["--db", str(tmp_path / "t.db"), *argv])


def write_trace(tmp_path, raw=None, name="trace.json"):
    f = tmp_path / name
    f.write_bytes(raw if raw is not None else trace(output={"msg": "hi", "n": 2}, trace_id="cli-1"))
    return str(f)


def test_cli_prints_a_valid_case_and_does_not_save(tmp_path, capsys):
    assert cli(tmp_path, "case", "from-trace", write_trace(tmp_path)) == 0
    captured = capsys.readouterr()
    case_file = tmp_path / "out.json"
    case_file.write_text(captured.out)
    case = load_case_file(str(case_file))
    assert case.case_id == "cli-1" and len(case.assertions) == 2
    cli(tmp_path, "case", "list")
    assert json.loads(capsys.readouterr().out) == []


def test_cli_save_overwrite_and_options(tmp_path, capsys):
    f = write_trace(tmp_path)
    assert cli(tmp_path, "case", "from-trace", f, "--save", "--case-id", "mine", "--name", "N") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["case_id"] == "mine" and out["saved"] is True
    assert cli(tmp_path, "case", "from-trace", f, "--save", "--case-id", "mine") == 2
    assert "--overwrite" in capsys.readouterr().err
    assert cli(tmp_path, "case", "from-trace", f, "--save", "--case-id", "mine", "--overwrite", "--path", "n") == 0
    capsys.readouterr()
    cli(tmp_path, "case", "show", "mine")
    shown = json.loads(capsys.readouterr().out)
    assert [a["path"] for a in shown["assertions"]] == ["n"]


def test_cli_notes_go_to_stderr_not_into_the_case(tmp_path, capsys):
    f = write_trace(tmp_path, trace(output={"a.b": 1, "ok": 2}, trace_id="n1"))
    assert cli(tmp_path, "case", "from-trace", f) == 0
    captured = capsys.readouterr()
    assert "skipped" in captured.err and json.loads(captured.out)["case_id"] == "n1"


@pytest.mark.parametrize("raw", [b"garbage", b'{"trace_id":"t","input":{},"output":{"n":NaN}}', b"x" * 1_000_001])
def test_cli_bad_trace_files_exit_2_without_traceback(tmp_path, capsys, raw):
    assert cli(tmp_path, "case", "from-trace", write_trace(tmp_path, raw)) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "Traceback" not in err


def test_cli_missing_file_exits_2(tmp_path, capsys):
    assert cli(tmp_path, "case", "from-trace", str(tmp_path / "nope.json")) == 2
    assert "error:" in capsys.readouterr().err


def test_headline_loop_trace_to_case_to_regression(tmp_path, capsys):
    """Capture good behaviour once, then catch a regression in the legacy runner."""
    request = {"action": "greet", "name": "Ava"}
    good_output = DeterministicLocalRunner().run(request)
    raw = json.dumps({"trace_id": "greet-ava", "input": request, "output": good_output}).encode()
    assert cli(tmp_path, "case", "from-trace", write_trace(tmp_path, raw), "--save") == 0
    assert cli(tmp_path, "run", "greet-ava", "--label", "good", "--runner", "local") == 0
    assert cli(tmp_path, "run", "greet-ava", "--label", "bad", "--runner", "local-legacy") == 1
    capsys.readouterr()
    assert cli(tmp_path, "compare", "1", "2") == 1  # regressed
