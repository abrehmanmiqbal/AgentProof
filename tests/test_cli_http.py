"""CLI wiring for HTTP adapters (same rules as subprocess adapters: explicit --config)."""
import json

import pytest
from test_http_adapter import (
    Handler,  # noqa: F401  (tests/ is on sys.path)
    server,  # noqa: F401  (fixture)
)

from agentproof.cli import main
from agentproof.storage import Repository

CASE = {
    "case_id": "web-case",
    "name": "web case",
    "input": {"q": "hi"},
    "assertions": [
        {"path": "status", "operator": "equals", "expected": "ok"},
        {"path": "echo.q", "operator": "equals", "expected": "hi"},
    ],
}


def cli(tmp_path, *argv):
    return main(["--db", str(tmp_path / "t.db"), *argv])


def setup(tmp_path, url, extra=""):
    case = tmp_path / "c.json"
    case.write_text(json.dumps(CASE))
    assert cli(tmp_path, "case", "add", str(case)) == 0
    cfg = tmp_path / "agentproof.toml"
    cfg.write_text(f'[adapters.web]\ntype = "http"\nurl = "{url}"\n{extra}\n')
    cfg.chmod(0o600)
    return str(cfg)


def test_run_through_http_adapter_records_metadata(tmp_path, server, capsys):  # noqa: F811
    cfg = setup(tmp_path, server + "/ok")
    capsys.readouterr()
    assert cli(tmp_path, "run", "web-case", "--label", "a", "--adapter", "web", "--config", cfg) == 0
    out = json.loads(capsys.readouterr().out)
    record = Repository(str(tmp_path / "t.db")).get_run(out["run_id"])
    assert out["passed"] is True and record.runner_name == "adapter:web"
    assert record.metadata.adapter_tier == "H" and record.metadata.exit_code == 200
    assert record.metadata.argv == ["POST", server + "/ok"]


def test_http_failures_are_recorded_failed_runs(tmp_path, server, capsys):  # noqa: F811
    cfg = setup(tmp_path, server + "/500")
    capsys.readouterr()
    assert cli(tmp_path, "run", "web-case", "--label", "a", "--adapter", "web", "--config", cfg) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["passed"] is False and "HTTP 500" in out["error"]
    record = Repository(str(tmp_path / "t.db")).get_run(out["run_id"])
    assert record.metadata.exit_code == 500


def test_run_all_with_repeat_works_for_http(tmp_path, server, capsys):  # noqa: F811
    cfg = setup(tmp_path, server + "/ok")
    capsys.readouterr()
    assert cli(tmp_path, "run-all", "--label", "v", "--adapter", "web", "--config", cfg, "--repeat", "2") == 0
    assert json.loads(capsys.readouterr().out)["passed"] == 1


def test_non_loopback_url_in_config_is_a_clean_exit_2(tmp_path, capsys):
    cfg = setup(tmp_path, "http://example.com/agent")
    capsys.readouterr()
    assert cli(tmp_path, "run", "web-case", "--label", "a", "--adapter", "web", "--config", cfg) == 2
    err = capsys.readouterr().err
    assert "allow_hosts" in err and "Traceback" not in err


@pytest.mark.parametrize("path", ["/redirect-nowhere", "/302"])
def test_redirect_is_a_failed_run_not_a_followed_request(tmp_path, server, capsys, path):  # noqa: F811
    cfg = setup(tmp_path, server + path)
    capsys.readouterr()
    assert cli(tmp_path, "run", "web-case", "--label", "a", "--adapter", "web", "--config", cfg) == 1
