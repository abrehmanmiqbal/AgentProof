"""CLI wiring for subprocess adapters (D-010 / D-012): explicit --config, no discovery, no mixing
with demo runners, adapter metadata recorded, every failure a clean exit code."""
import json
import sys

import pytest
from test_subprocess_adapter import AGENT, PYTHON  # sibling test module (tests/ is on sys.path)

from regressagent.cli import main
from regressagent.storage import Repository

pytestmark = [
    pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Tier A adapters are Linux only"),
    pytest.mark.skipif(not PYTHON, reason="no usable interpreter for the test agent"),
]

CASE = {
    "case_id": "adapter-case",
    "name": "adapter case",
    "input": {"mode": "ok", "tag": "x"},
    "assertions": [
        {"path": "status", "operator": "equals", "expected": "ok"},
        {"path": "echo.tag", "operator": "equals", "expected": "x"},
    ],
}


def cli(tmp_path, *argv):
    return main(["--db", str(tmp_path / "t.db"), *argv])


def write_case(tmp_path, case=None, name="c.json"):
    f = tmp_path / name
    f.write_text(json.dumps(case or CASE))
    return str(f)


def write_config(tmp_path, name="hostile", timeout=5, ack="true", fname="regressagent.toml"):
    f = tmp_path / fname
    f.write_text(
        f"[adapters.{name}]\n"
        'tier = "A"\n'
        f"argv = [{json.dumps(PYTHON)}, {json.dumps(AGENT)}]\n"
        f"timeout_seconds = {timeout}\n"
        f"acknowledge_not_sandboxed = {ack}\n"
    )
    f.chmod(0o600)
    return str(f)


def setup(tmp_path, case=None):
    assert cli(tmp_path, "case", "add", write_case(tmp_path, case)) == 0
    return write_config(tmp_path)


def test_run_with_adapter_passes_and_records_metadata(tmp_path, capsys):
    cfg = setup(tmp_path)
    capsys.readouterr()
    code = cli(tmp_path, "run", "adapter-case", "--label", "a", "--adapter", "hostile", "--config", cfg)
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["passed"] is True
    record = Repository(str(tmp_path / "t.db")).get_run(out["run_id"])
    assert record.runner_name == "adapter:hostile"
    assert record.metadata is not None
    assert record.metadata.adapter_name == "hostile" and record.metadata.adapter_tier == "A"
    assert record.metadata.exit_code == 0
    assert record.metadata.executable_sha256


def test_failing_assertion_through_adapter_exits_1(tmp_path):
    bad = {**CASE, "assertions": [{"path": "status", "operator": "equals", "expected": "nope"}]}
    cfg = setup(tmp_path, bad)
    assert cli(tmp_path, "run", "adapter-case", "--label", "a", "--adapter", "hostile", "--config", cfg) == 1


def test_hostile_agent_is_a_recorded_failed_run_not_a_crash(tmp_path, capsys):
    cfg = setup(tmp_path, {**CASE, "input": {"mode": "exit_nonzero"}})
    capsys.readouterr()
    code = cli(tmp_path, "run", "adapter-case", "--label", "a", "--adapter", "hostile", "--config", cfg)
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["passed"] is False and out["error"]
    record = Repository(str(tmp_path / "t.db")).get_run(out["run_id"])
    assert record.metadata is not None and record.metadata.exit_code not in (None, 0)


def test_run_all_and_repeat_work_with_adapter(tmp_path, capsys):
    cfg = setup(tmp_path)
    capsys.readouterr()
    assert cli(tmp_path, "run-all", "--label", "v", "--adapter", "hostile", "--config", cfg, "--repeat", "2") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["passed"] == 1 and len(out["results"][0]["run_ids"]) == 2
    repo = Repository(str(tmp_path / "t.db"))
    for run_id in out["results"][0]["run_ids"]:
        assert repo.get_run(run_id).metadata is not None


@pytest.mark.parametrize(
    ("extra", "needle"),
    [
        (["--adapter", "hostile"], "--config"),  # adapter without config
        (["--adapter", "hostile", "--config", "CFG", "--runner", "local"], "--runner"),  # mixing
        (["--config", "CFG"], "--adapter"),  # config without adapter
        (["--adapter", "nope", "--config", "CFG"], "hostile"),  # unknown adapter lists known ones
        (["--adapter", "hostile", "--config", "MISSING"], "config"),  # unreadable config
    ],
)
def test_bad_adapter_arguments_exit_2_and_record_nothing(tmp_path, capsys, extra, needle):
    cfg = setup(tmp_path)
    argv = [cfg if a == "CFG" else str(tmp_path / "nope.toml") if a == "MISSING" else a for a in extra]
    capsys.readouterr()
    assert cli(tmp_path, "run", "adapter-case", "--label", "a", *argv) == 2
    err = capsys.readouterr().err
    assert needle in err and "Traceback" not in err
    assert Repository(str(tmp_path / "t.db")).list_runs("adapter-case") == []


def test_config_without_acknowledgement_is_refused(tmp_path, capsys):
    setup(tmp_path)
    cfg = write_config(tmp_path, ack="false", fname="noack.toml")
    capsys.readouterr()
    assert cli(tmp_path, "run", "adapter-case", "--label", "a", "--adapter", "hostile", "--config", cfg) == 2
    assert "acknowledge_not_sandboxed" in capsys.readouterr().err


def test_regressagent_toml_in_cwd_is_never_discovered(tmp_path, monkeypatch, capsys):
    setup(tmp_path)  # writes tmp_path/regressagent.toml
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    assert cli(tmp_path, "run", "adapter-case", "--label", "a", "--adapter", "hostile") == 2
    assert "--config" in capsys.readouterr().err
