"""Secret redaction of stored outputs (THREAT_MODEL #8). Best-effort, not a guarantee.

Every "secret" here is fake and assembled at runtime from fragments, so this file contains no
real-looking credential literal (secret scanners / push protection stay quiet)."""
import json
import sqlite3
import time

import pytest

from regressagent import cli
from regressagent.models import (
    AssertionOperator,
    AssertionResult,
    AssertionSpec,
    RegressionCase,
    RegressionResult,
    RunMetadata,
)
from regressagent.redaction import Redactor
from regressagent.regression import RegressionEngine
from regressagent.runner import DeterministicLocalRunner
from regressagent.storage import Repository

ALPHA = "A1b2C3d4E5f6G7h8I9j0K"


def body(n, alphabet=ALPHA):
    return (alphabet * (n // len(alphabet) + 1))[:n]


GH_CLASSIC = "gh" + "p_" + body(36)
GH_PAT = "github" + "_pat_" + body(22) + "_" + body(59)
AWS_KEY = "AK" + "IA" + body(16, "ABCDEFGH12345678")
OPENAI = "s" + "k-" + body(32)
OPENAI_PROJ = "s" + "k-proj-" + body(40, "AbCd_Ef-12")
ANTHROPIC = "s" + "k-ant-" + body(40, "AbCd_Ef-12")
SLACK = "xo" + "xb-" + "1234567890-" + body(24)
GOOGLE = "AI" + "za" + body(35, "AbCd_Ef-12")
JWT = "ey" + "J" + body(20) + ".ey" + "J" + body(20) + "." + body(20)
PEM = (
    "-----BEGIN " + "RSA PRIVATE KEY-----\n" + body(64) + "\n" + body(64)
    + "\n-----END " + "RSA PRIVATE KEY-----"
)
PEM_TRUNCATED = "-----BEGIN " + "PRIVATE KEY-----\n" + body(200)
BEARER = "Bearer " + body(40, "AbCd.Ef-12_")
URL_PASSWORD = "p4ssw0rd-" + body(10)

SECRET_SAMPLES = {
    "github-classic": GH_CLASSIC,
    "github-pat": GH_PAT,
    "aws": AWS_KEY,
    "openai": OPENAI,
    "openai-proj": OPENAI_PROJ,
    "anthropic": ANTHROPIC,
    "slack": SLACK,
    "google": GOOGLE,
    "jwt": JWT,
    "pem": PEM,
}


def make_case(case_id="c1", extra_input=None):
    inp = {"action": "echo"}
    inp.update(extra_input or {})
    return RegressionCase(
        case_id=case_id,
        name="n",
        input=inp,
        assertions=[AssertionSpec(path="action", operator=AssertionOperator.EQUALS, expected="echo")],
    )


# ---- known token patterns ------------------------------------------------------------
@pytest.mark.parametrize("kind", sorted(SECRET_SAMPLES))
def test_known_token_formats_are_redacted_in_surrounding_text(kind):
    secret = SECRET_SAMPLES[kind]
    out = Redactor().text(f"before {secret} after")
    assert secret not in out
    assert out.startswith("before ") and out.endswith(" after")
    assert "[REDACTED" in out


def test_pem_block_without_end_marker_is_redacted_to_end_of_text():
    out = Redactor().text("x " + PEM_TRUNCATED)
    assert body(200) not in out
    assert "[REDACTED" in out


def test_bearer_authorization_header_is_redacted():
    out = Redactor().text("Authorization: " + BEARER + "\nnext line")
    assert BEARER.split(" ", 1)[1] not in out
    assert "next line" in out


def test_url_password_is_redacted_but_user_and_host_survive():
    out = Redactor().text(f"connect postgres://alice:{URL_PASSWORD}@db.example.com:5432/app now")
    assert URL_PASSWORD not in out
    assert "alice" in out and "db.example.com" in out


@pytest.mark.parametrize(
    "template",
    [
        "password={v}",
        "PASSWORD: {v}",
        '"password": "{v}"',
        "'api_key': '{v}'",
        "x-api-key={v}",
        "client_secret = {v}",
        "access-token:{v}",
        "my_secret_key={v}",
    ],
)
def test_key_value_assignments_with_sensitive_names_are_redacted(template):
    value = "hunter2-" + body(12)
    out = Redactor().text("log: " + template.format(v=value) + " end")
    assert value not in out
    assert out.startswith("log: ") and out.endswith(" end")


# ---- no needless damage --------------------------------------------------------------
@pytest.mark.parametrize(
    "benign",
    [
        "Hello, Ava!",
        "max_tokens: 100",
        "token_count=5",
        "tokenizer: gpt-style",
        "The password policy requires 12 characters.",
        "https://example.com/path?q=1&r=2",
        "mail me at ava@example.com",
        "da39a3ee5e6b4b0d3255bfef95601890afd80709",  # a git SHA-1
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # a SHA-256
        "123e4567-e89b-12d3-a456-426614174000",
        "task-based-tokenization-pipeline-stage-two",
        "AKIA is a prefix, AKIAshort is not a key",
        "secretary: Dana",
        "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
    ],
)
def test_benign_text_is_left_unchanged(benign):
    assert Redactor().text(benign) == benign


def test_redaction_is_idempotent():
    r = Redactor()
    blob = " | ".join(
        [*SECRET_SAMPLES.values(), BEARER, "password=hunter2-abcdef", "http://u:" + URL_PASSWORD + "@h/"]
    )
    once = r.text(blob)
    assert r.text(once) == once


# ---- environment based ---------------------------------------------------------------
def test_values_of_sensitive_environment_variables_are_redacted_anywhere():
    env = {
        "SERVICE_TOKEN": "tok-" + body(20, "xyz987"),
        "DB_PASSWORD": "pw-" + body(12, "qrs654"),
        "AWS_SECRET_ACCESS_KEY": body(30, "mnp321"),
        "OPENAI_API_KEY": "key-" + body(25, "uvw111"),
        "GPG_KEY": body(16, "ghi222"),
    }
    r = Redactor(environ=env)
    for name, secret in env.items():
        out = r.text(f"leak {secret} and again {secret}.")
        assert secret not in out, name
        assert "leak " in out and "and again" in out


def test_environment_values_that_are_not_secret_named_or_too_short_are_kept():
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/home/someone-long-name",
        "AUTHOR_NAME": "Jonathan Smith",
        "SSH_AUTH_SOCK": "/tmp/ssh-agent-socket-path",
        "PWD": "/work/project-directory",
        "SHORT_TOKEN": "abc",  # < 8 chars: redacting it would mangle ordinary text
        "EMPTY_SECRET": "",
    }
    r = Redactor(environ=env)
    for value in env.values():
        assert r.text(f"x {value} y") == f"x {value} y"


def test_longer_environment_secret_wins_over_a_shorter_one_containing_it():
    env = {"A_TOKEN": "prefix-secret", "B_TOKEN": "prefix-secret-extended-tail"}
    out = Redactor(environ=env).text("v=prefix-secret-extended-tail")
    assert "extended" not in out and "tail" not in out


def test_from_environ_reads_the_live_process_environment(monkeypatch):
    monkeypatch.setenv("LIVE_TEST_TOKEN", "live-" + body(20, "pqr555"))
    out = Redactor.from_environ().text("v=" + "live-" + body(20, "pqr555"))
    assert "pqr555" not in out


# ---- structured values ---------------------------------------------------------------
def test_values_under_sensitive_keys_are_redacted_regardless_of_shape():
    data = {
        "password": "x",
        "nested": {"apiKey": 123456, "Authorization": "short", "x-api-key": "k"},
        "list": [{"client_secret": ["a", "b", {"deep": "c"}]}],
        "keep": "visible",
        "token_count": 5,
        "max_tokens": 100,
        "flag": {"secret": True, "token": None},
    }
    out = Redactor().value(data)
    assert out["password"] != "x" and "REDACTED" in out["password"]
    assert "REDACTED" in out["nested"]["apiKey"] if isinstance(out["nested"]["apiKey"], str) else False
    assert "REDACTED" in out["nested"]["Authorization"] and "REDACTED" in out["nested"]["x-api-key"]
    leaves = json.dumps(out["list"])
    assert '"a"' not in leaves and '"b"' not in leaves and '"c"' not in leaves
    assert out["keep"] == "visible" and out["token_count"] == 5 and out["max_tokens"] == 100
    # booleans and null carry no secret and keep their type
    assert out["flag"] == {"secret": True, "token": None}


def test_secret_shaped_values_are_redacted_deep_inside_structures_and_dict_keys():
    data = {"a": [{"b": f"v {GH_CLASSIC}"}], GH_CLASSIC: "k", "n": 7, "ok": True}
    out = Redactor().value(data)
    dumped = json.dumps(out)
    assert GH_CLASSIC not in dumped
    assert out["n"] == 7 and out["ok"] is True


def test_dict_key_collisions_after_redaction_do_not_lose_values():
    k1 = "gh" + "p_" + body(36)
    k2 = "gh" + "p_" + body(36, "ZYXWVU98765432")
    out = Redactor().value({k1: "one", k2: "two"})
    assert sorted(out.values()) == ["one", "two"]


def test_unsupported_types_fail_closed_instead_of_passing_through():
    out = Redactor().value({"x": {1, 2}, "y": object()})
    assert "REDACTED" in json.dumps(out)


def test_extremely_deep_structure_fails_closed_without_crashing():
    deep: object = "leaf-" + GH_CLASSIC
    for _ in range(5000):
        deep = {"k": deep}
    out = Redactor().value(deep)  # must not raise RecursionError
    assert GH_CLASSIC not in repr(out)[:100000]


def test_result_redaction_keeps_the_verdict_and_scrubs_every_value_field():
    result = RegressionResult(
        case_id="c1",
        passed=False,
        output={"echo": {"token": "abc", "msg": f"hi {GH_CLASSIC}"}},
        assertions=[
            AssertionResult(
                path="auth.token",
                operator=AssertionOperator.EQUALS,
                passed=False,
                expected="expected-secret-value",
                actual="actual-secret-value",
                message="Values are not equal",
            ),
            AssertionResult(
                path="msg", operator=AssertionOperator.CONTAINS, passed=True,
                expected="hi", actual=f"hi {GH_CLASSIC}", message="Expected value is contained",
            ),
        ],
        error=f"Runner raised RuntimeError: boom {OPENAI}",
    )
    out = Redactor().result(result)
    dumped = out.model_dump_json()
    for secret in (GH_CLASSIC, OPENAI, "actual-secret-value", "expected-secret-value"):
        assert secret not in dumped
    assert out.passed is False and out.case_id == "c1"
    assert [a.passed for a in out.assertions] == [False, True]
    assert out.assertions[0].message == "Values are not equal"
    assert out.assertions[1].path == "msg" and out.assertions[1].expected == "hi"


# ---- argv ---------------------------------------------------------------------------
def test_argv_values_that_look_like_credentials_are_redacted():
    argv = [
        "/usr/bin/python3", "agent.py",
        "--token=" + body(20, "abc123"),
        "--api-key", "separate-" + body(15, "def456"),
        "--password", "hunter2!",
        GH_CLASSIC,
        "--model", "small",
    ]
    out = Redactor().argv(argv)
    dumped = json.dumps(out)
    assert body(20, "abc123") not in dumped and body(15, "def456") not in dumped
    assert "hunter2!" not in dumped and GH_CLASSIC not in dumped
    assert out[:2] == ["/usr/bin/python3", "agent.py"]
    assert out[-2:] == ["--model", "small"]
    assert len(out) == len(argv)


# ---- hostile inputs: speed ------------------------------------------------------------
HOSTILE = {
    "megabyte_of_a": "A" * 1_000_000,
    "begin_markers": "-----BEGIN " * 90_000,
    "begin_then_long_name": "-----BEGIN " + "A" * 1_000_000,
    "password_equals_spam": "password=" * 110_000,
    "password_then_spaces": "password" + " " * 1_000_000,
    "bearer_spam": "Bearer " * 140_000,
    "url_scheme_spam": "a://" * 250_000,
    "at_sign_run": "a" * 500_000 + "@" * 500_000,
    "sk_dash_run": "sk-" + "a-" * 500_000,
    "ghp_then_short": ("gh" + "p_a") * 300_000,
    "eyJ_dots": ("ey" + "J.") * 400_000,
    "quote_colon_run": '"token":' * 120_000,
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_hostile_text_is_processed_quickly(name):
    start = time.perf_counter()
    Redactor(environ={"X_TOKEN": "x" * 40}).text(HOSTILE[name])
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"{name} took {elapsed:.2f}s"


# ---- documented limits (pinned so a change is a conscious decision) -------------------
def test_known_limit_secret_split_by_zero_width_character_is_not_detected():
    split = GH_CLASSIC[:10] + "\u200b" + GH_CLASSIC[10:]
    assert Redactor().text(split) == split


def test_known_limit_short_unprefixed_free_text_secret_is_not_detected():
    assert Redactor().text("password=abc") == "password=abc"
    assert Redactor().text("the key is correcthorse") == "the key is correcthorse"


# ---- storage chokepoint -------------------------------------------------------------
def test_record_run_never_stores_the_raw_secret(tmp_path):
    path = tmp_path / "r.db"
    case = make_case()
    result = RegressionResult(
        case_id="c1", passed=True, output={"echo": {"auth": GH_CLASSIC, "n": 1}, "action": "echo"},
        assertions=[
            AssertionResult(path="action", operator=AssertionOperator.EQUALS, passed=True,
                            expected="echo", actual="echo", message="Values are equal")
        ],
        error=None,
    )
    with Repository(path) as repo:
        repo.save_case(case)
        rid = repo.record_run(case, result, label="a", runner_name="local")
        stored = repo.get_run(rid)
    assert GH_CLASSIC not in stored.result.model_dump_json()
    assert stored.result.passed is True and stored.result.output["echo"]["n"] == 1
    assert GH_CLASSIC.encode() not in path.read_bytes()
    conn = sqlite3.connect(path)
    try:
        assert GH_CLASSIC not in conn.execute("SELECT result_json FROM runs").fetchone()[0]
    finally:
        conn.close()


def test_record_run_redacts_metadata_argv_and_uses_the_repository_redactor(tmp_path):
    path = tmp_path / "m.db"
    case = make_case()
    result = RegressionEngine(DeterministicLocalRunner()).run_case(case)
    secret = "envsecret-" + body(20, "lmn777")
    meta = RunMetadata(
        adapter_name="a", adapter_tier="A",
        argv=["/bin/true", "--api-key", "argsecret-" + body(12, "stu888"), "plain-" + secret],
    )
    with Repository(path, redactor=Redactor(environ={"MY_API_KEY": secret})) as repo:
        repo.save_case(case)
        rid = repo.record_run(case, result, label="a", runner_name="a", metadata=meta)
        stored = repo.get_run(rid)
    dumped = stored.metadata.model_dump_json()
    assert "stu888" not in dumped and secret not in dumped
    assert stored.metadata.argv[0] == "/bin/true"


def test_default_repository_redactor_reads_the_environment_at_record_time(tmp_path, monkeypatch):
    path = tmp_path / "e.db"
    case = make_case()
    secret = "late-" + body(24, "wxy444")
    result = RegressionResult(case_id="c1", passed=True, output={"v": secret, "action": "echo"})
    with Repository(path) as repo:
        repo.save_case(case)
        monkeypatch.setenv("LATE_SET_SECRET", secret)  # set after the Repository was created
        rid = repo.record_run(case, result, label="a", runner_name="local")
        assert secret not in repo.get_run(rid).result.model_dump_json()


# ---- CLI end to end ---------------------------------------------------------------
def test_cli_run_stores_and_prints_only_redacted_data(tmp_path, capsys):
    case_file = tmp_path / "case.json"
    case_file.write_text(json.dumps({
        "case_id": "leaky", "name": "echoes its input",
        "input": {"action": "echo", "note": GH_CLASSIC},
        "assertions": [{"path": "action", "operator": "equals", "expected": "echo"}],
    }))
    db = str(tmp_path / "cli.db")
    assert cli.main(["--db", db, "case", "add", str(case_file)]) == 0
    assert cli.main(["--db", db, "run", "leaky", "--label", "a"]) == 0
    assert cli.main(["--db", db, "run", "leaky", "--label", "b"]) == 0
    assert cli.main(["--db", db, "report", "1", "2", "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert GH_CLASSIC not in captured.out and GH_CLASSIC not in captured.err
    conn = sqlite3.connect(db)
    try:
        rows = [r[0] for r in conn.execute("SELECT result_json FROM runs")]
    finally:
        conn.close()
    assert len(rows) == 2 and all(GH_CLASSIC not in r for r in rows)


def test_cli_run_error_text_from_a_failing_runner_is_redacted(tmp_path, capsys, monkeypatch):
    class Leaky:
        def run(self, _input):
            raise RuntimeError(f"auth failed for {GH_CLASSIC}")

    monkeypatch.setitem(cli.RUNNERS, "leaky", Leaky)
    case_file = tmp_path / "case.json"
    case_file.write_text(json.dumps({
        "case_id": "c", "name": "n", "input": {"action": "echo"},
        "assertions": [{"path": "action", "operator": "equals", "expected": "echo"}],
    }))
    db = str(tmp_path / "cli.db")
    assert cli.main(["--db", db, "case", "add", str(case_file)]) == 0
    capsys.readouterr()
    code = cli.main(["--db", db, "run", "c", "--label", "a", "--runner", "leaky"])
    out = capsys.readouterr()
    assert code == 1
    assert GH_CLASSIC not in out.out and GH_CLASSIC not in out.err
    assert "auth failed" in out.out  # the explanation is kept; only the secret is removed
