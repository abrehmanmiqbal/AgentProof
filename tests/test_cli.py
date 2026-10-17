import json

from agentproof.cli import main

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
