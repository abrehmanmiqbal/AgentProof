import json

import pytest

from regressagent.cli import main

CASE = {
    "case_id": "greet-ava",
    "name": "Greet Ava",
    "input": {"action": "greet", "name": "Ava"},
    "assertions": [
        {"path": "message", "operator": "equals", "expected": "Hello, Ava!"},
        {"path": "action", "operator": "equals", "expected": "greet"},
    ],
}


def cli(tmp_path, *argv):
    return main(["--db", str(tmp_path / "t.db"), *argv])


def write_case(tmp_path, data=None, name="case.json"):
    f = tmp_path / name
    f.write_text(json.dumps(data or CASE))
    return str(f)


def test_demo_still_works(capsys):
    assert main(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True


def test_full_loop_failure_to_fix_to_compare(tmp_path, capsys):
    assert cli(tmp_path, "case", "add", write_case(tmp_path)) == 0
    assert cli(tmp_path, "run", "greet-ava", "--label", "before", "--runner", "local-legacy") == 1
    assert cli(tmp_path, "run", "greet-ava", "--label", "after", "--runner", "local") == 0
    capsys.readouterr()
    assert cli(tmp_path, "compare", "1", "2") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "improved"
    assert out["same_case_definition"] is True


def test_compare_exits_nonzero_when_regressed(tmp_path, capsys):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    cli(tmp_path, "run", "greet-ava", "--label", "good", "--runner", "local")
    cli(tmp_path, "run", "greet-ava", "--label", "bad", "--runner", "local-legacy")
    capsys.readouterr()
    assert cli(tmp_path, "compare", "1", "2") == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "regressed"


def test_list_and_show_and_runs(tmp_path, capsys):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    cli(tmp_path, "run", "greet-ava", "--label", "a")
    capsys.readouterr()
    assert cli(tmp_path, "case", "list") == 0
    assert json.loads(capsys.readouterr().out) == ["greet-ava"]
    assert cli(tmp_path, "case", "show", "greet-ava") == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Greet Ava"
    assert cli(tmp_path, "runs", "greet-ava") == 0
    assert json.loads(capsys.readouterr().out)[0]["label"] == "a"


def test_duplicate_add_is_refused_then_overwrite_allowed(tmp_path, capsys):
    f = write_case(tmp_path)
    assert cli(tmp_path, "case", "add", f) == 0
    assert cli(tmp_path, "case", "add", f) == 2
    assert "already exists" in capsys.readouterr().err
    assert cli(tmp_path, "case", "add", f, "--overwrite") == 0


def test_malformed_and_hostile_case_files_rejected_cleanly(tmp_path, capsys):
    for bad in [
        {"case_id": "", "name": "n", "input": {}, "assertions": []},
        {**CASE, "extra_field": "__import__('os').system('echo pwned')"},
        {**CASE, "assertions": [{"path": "a", "operator": "eval", "expected": 1}]},
    ]:
        assert cli(tmp_path, "case", "add", write_case(tmp_path, bad, "bad.json")) == 2
        assert "Invalid case file" in capsys.readouterr().err
    (tmp_path / "junk.json").write_text("{not json")
    assert cli(tmp_path, "case", "add", str(tmp_path / "junk.json")) == 2
    assert cli(tmp_path, "case", "add", str(tmp_path / "missing.json")) == 2


def test_oversized_case_file_rejected_without_full_parse(tmp_path, capsys):
    big = {**CASE, "input": {"blob": "x" * 1_100_000}}
    assert cli(tmp_path, "case", "add", write_case(tmp_path, big, "big.json")) == 2
    assert "exceeds" in capsys.readouterr().err


def test_run_unknown_case_is_predictable_error(tmp_path, capsys):
    assert cli(tmp_path, "run", "nope", "--label", "a") == 2
    assert "not found" in capsys.readouterr().err


def test_corrupt_db_is_predictable_cli_error(tmp_path, capsys):
    bad = tmp_path / "bad.db"
    bad.write_text("not a db")
    assert main(["--db", str(bad), "case", "list"]) == 2
    assert "error:" in capsys.readouterr().err


ECHO_CASE = {
    "case_id": "echo-x",
    "name": "Echo",
    "input": {"action": "echo", "x": 1},
    "assertions": [{"path": "action", "operator": "equals", "expected": "echo"}],
}


def test_case_delete_requires_yes_and_keeps_data(tmp_path, capsys):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    cli(tmp_path, "run", "greet-ava", "--label", "a")
    capsys.readouterr()
    assert cli(tmp_path, "case", "delete", "greet-ava") == 2
    assert "--yes" in capsys.readouterr().err
    assert cli(tmp_path, "case", "list") == 0
    assert json.loads(capsys.readouterr().out) == ["greet-ava"]


def test_case_delete_with_yes_removes_case_and_runs(tmp_path, capsys):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    cli(tmp_path, "run", "greet-ava", "--label", "a")
    cli(tmp_path, "run", "greet-ava", "--label", "b")
    capsys.readouterr()
    assert cli(tmp_path, "case", "delete", "greet-ava", "--yes") == 0
    assert json.loads(capsys.readouterr().out) == {"deleted": "greet-ava", "runs_deleted": 2}
    cli(tmp_path, "case", "list")
    assert json.loads(capsys.readouterr().out) == []
    assert cli(tmp_path, "compare", "1", "2") == 2  # runs are gone too


def test_case_delete_unknown_case_is_clean_error(tmp_path, capsys):
    capsys.readouterr()
    assert cli(tmp_path, "case", "delete", "nope", "--yes") == 2
    assert "not found" in capsys.readouterr().err


def _two_cases(tmp_path):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    cli(tmp_path, "case", "add", write_case(tmp_path, ECHO_CASE, "echo.json"))


def test_run_all_records_every_case_and_exits_zero_when_all_pass(tmp_path, capsys):
    _two_cases(tmp_path)
    capsys.readouterr()
    assert cli(tmp_path, "run-all", "--label", "v1") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["total"] == 2 and out["passed"] == 2 and out["failed"] == 0
    assert [r["case_id"] for r in out["results"]] == ["echo-x", "greet-ava"]
    assert all(isinstance(r["run_id"], int) for r in out["results"])
    assert cli(tmp_path, "runs", "echo-x") == 0
    assert json.loads(capsys.readouterr().out)[0]["label"] == "v1"


def test_run_all_exits_one_if_any_case_fails_but_still_runs_the_rest(tmp_path, capsys):
    _two_cases(tmp_path)
    capsys.readouterr()
    assert cli(tmp_path, "run-all", "--label", "old", "--runner", "local-legacy") == 1
    out = json.loads(capsys.readouterr().out)
    assert out["passed"] == 1 and out["failed"] == 1
    by_id = {r["case_id"]: r for r in out["results"]}
    assert by_id["greet-ava"]["passed"] is False
    assert by_id["echo-x"]["passed"] is True


def test_run_all_with_no_cases_is_an_error_not_a_silent_pass(tmp_path, capsys):
    capsys.readouterr()
    assert cli(tmp_path, "run-all", "--label", "v1") == 2
    assert "no cases" in capsys.readouterr().err.lower()


def _improved_pair(tmp_path):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    cli(tmp_path, "run", "greet-ava", "--label", "b", "--runner", "local-legacy")
    cli(tmp_path, "run", "greet-ava", "--label", "a", "--runner", "local")


def test_report_output_writes_file_identical_to_stdout_render(tmp_path, capsys):
    _improved_pair(tmp_path)
    capsys.readouterr()
    assert cli(tmp_path, "report", "1", "2") == 0
    expected = capsys.readouterr().out
    target = tmp_path / "r.md"
    assert cli(tmp_path, "report", "1", "2", "--output", str(target)) == 0
    assert target.read_text(encoding="utf-8") == expected
    assert str(target) in capsys.readouterr().out


def test_report_output_refuses_overwrite_without_force(tmp_path, capsys):
    _improved_pair(tmp_path)
    target = tmp_path / "r.md"
    target.write_text("precious")
    capsys.readouterr()
    assert cli(tmp_path, "report", "1", "2", "--output", str(target)) == 2
    assert "--force" in capsys.readouterr().err
    assert target.read_text() == "precious"
    assert cli(tmp_path, "report", "1", "2", "--output", str(target), "--force") == 0
    assert target.read_text().startswith("# RegressAgent report")


def test_report_output_bad_path_is_clean_error(tmp_path, capsys):
    _improved_pair(tmp_path)
    capsys.readouterr()
    missing = tmp_path / "no_such_dir" / "r.md"
    assert cli(tmp_path, "report", "1", "2", "--output", str(missing)) == 2
    assert "error:" in capsys.readouterr().err


def test_report_output_keeps_regression_exit_code(tmp_path, capsys):
    _improved_pair(tmp_path)
    target = tmp_path / "r.json"
    assert cli(tmp_path, "report", "2", "1", "--format", "json", "--output", str(target)) == 1
    assert json.loads(target.read_text())["verdict"] == "regressed"


def test_run_repeat_records_each_run_and_reports_stability(tmp_path, capsys):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    capsys.readouterr()
    assert cli(tmp_path, "run", "greet-ava", "--label", "r", "--repeat", "3") == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"run_ids": [1, 2, 3], "total": 3, "passed": 3, "failed": 0, "stable": True}
    assert cli(tmp_path, "runs", "greet-ava") == 0
    assert len(json.loads(capsys.readouterr().out)) == 3


def test_run_default_output_format_unchanged(tmp_path, capsys):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    capsys.readouterr()
    assert cli(tmp_path, "run", "greet-ava", "--label", "r") == 0
    assert set(json.loads(capsys.readouterr().out)) == {"run_id", "passed", "error"}


def test_run_repeat_detects_flaky_runner(tmp_path, capsys, monkeypatch):
    from regressagent.runner import RUNNERS, DeterministicLocalRunner

    class Flaky(DeterministicLocalRunner):
        calls = 0

        def run(self, input_data):
            Flaky.calls += 1
            out = super().run(input_data)
            if Flaky.calls % 3 == 0:  # every third run gives a wrong answer
                out = {**out, "message": "Hi!"}
            return out

    monkeypatch.setitem(RUNNERS, "flaky", Flaky)
    cli(tmp_path, "case", "add", write_case(tmp_path))
    capsys.readouterr()
    assert cli(tmp_path, "run", "greet-ava", "--label", "f", "--runner", "flaky", "--repeat", "3") == 1
    out = json.loads(capsys.readouterr().out)
    assert out["passed"] == 2 and out["failed"] == 1
    assert out["stable"] is False


def test_run_repeat_out_of_range_is_rejected(tmp_path, capsys):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    for bad in ("0", "-1", "21", "abc"):
        try:
            cli(tmp_path, "run", "greet-ava", "--label", "r", "--repeat", bad)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError(f"--repeat {bad} was accepted")
    capsys.readouterr()
    cli(tmp_path, "runs", "greet-ava")
    assert json.loads(capsys.readouterr().out) == []  # nothing was recorded


# ---------------------------------------------------------------- run-all --repeat
def _two_greet_cases(tmp_path):
    other = {**CASE, "case_id": "greet-bob", "input": {"action": "greet", "name": "Bob"}}
    other["assertions"] = [{"path": "message", "operator": "equals", "expected": "Hello, Bob!"}]
    cli(tmp_path, "case", "add", write_case(tmp_path))
    cli(tmp_path, "case", "add", write_case(tmp_path, other, name="b.json"))


def test_run_all_default_output_shape_is_unchanged(tmp_path, capsys):
    _two_greet_cases(tmp_path)
    capsys.readouterr()
    assert cli(tmp_path, "run-all", "--label", "v") == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"total", "passed", "failed", "results"}
    assert set(out["results"][0]) == {"case_id", "run_id", "passed", "error"}


def test_run_all_repeat_records_n_runs_per_case(tmp_path, capsys):
    _two_greet_cases(tmp_path)
    capsys.readouterr()
    assert cli(tmp_path, "run-all", "--label", "v", "--repeat", "3") == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["total"], out["passed"], out["failed"]) == (2, 2, 0)
    assert out["unstable"] == []
    for entry in out["results"]:
        assert len(entry["run_ids"]) == 3
        assert (entry["total"], entry["passed"], entry["failed"]) == (3, 3, 0)
        assert entry["stable"] is True
    cli(tmp_path, "runs", "greet-ava")
    assert len(json.loads(capsys.readouterr().out)) == 3


def test_run_all_repeat_flags_unstable_case_and_exits_1(tmp_path, capsys, monkeypatch):
    from regressagent.runner import RUNNERS, DeterministicLocalRunner

    class Flaky(DeterministicLocalRunner):
        calls = 0

        def run(self, input_data):
            Flaky.calls += 1
            out = super().run(input_data)
            return {**out, "message": "Hi!"} if Flaky.calls % 3 == 0 else out

    monkeypatch.setitem(RUNNERS, "flaky", Flaky)
    cli(tmp_path, "case", "add", write_case(tmp_path))
    capsys.readouterr()
    assert cli(tmp_path, "run-all", "--label", "f", "--runner", "flaky", "--repeat", "3") == 1
    out = json.loads(capsys.readouterr().out)
    assert (out["total"], out["passed"], out["failed"]) == (1, 0, 1)
    assert out["unstable"] == ["greet-ava"]
    entry = out["results"][0]
    assert (entry["passed"], entry["failed"], entry["stable"]) == (2, 1, False)


def test_run_all_repeat_out_of_range_is_rejected_and_records_nothing(tmp_path, capsys):
    cli(tmp_path, "case", "add", write_case(tmp_path))
    for bad in ("0", "21", "abc"):
        with pytest.raises(SystemExit) as exc:
            cli(tmp_path, "run-all", "--label", "r", "--repeat", bad)
        assert exc.value.code == 2
    capsys.readouterr()
    cli(tmp_path, "runs", "greet-ava")
    assert json.loads(capsys.readouterr().out) == []


# ---------------------------------------------------------------- oversized runner output
def test_oversized_runner_output_is_recorded_as_failed_run(tmp_path, capsys, monkeypatch):
    from regressagent.runner import RUNNERS, DeterministicLocalRunner

    class Huge(DeterministicLocalRunner):
        def run(self, input_data):
            return {"message": "x" * 2_000_000, "action": "greet"}

    monkeypatch.setitem(RUNNERS, "huge", Huge)
    cli(tmp_path, "case", "add", write_case(tmp_path))
    capsys.readouterr()
    assert cli(tmp_path, "run", "greet-ava", "--label", "h", "--runner", "huge") == 1
    out = json.loads(capsys.readouterr().out)
    assert out["passed"] is False
    assert "exceeds" in out["error"]
    cli(tmp_path, "runs", "greet-ava")
    runs = json.loads(capsys.readouterr().out)
    assert len(runs) == 1 and runs[0]["passed"] is False  # recorded, not lost
