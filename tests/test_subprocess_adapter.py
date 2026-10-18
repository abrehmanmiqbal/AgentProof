"""Tier A subprocess adapter tests against a purpose-built hostile agent (D-010, section 7).

Every hostile behaviour must end in a *failed recorded result* (an AdapterError that the engine
turns into ``passed=False``), never in a hang, a crash or a leftover process. Tier A is NOT a
sandbox: tests for things it does not block assert exactly that, so the docs stay honest.
"""
import hashlib
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

import pytest

from agentproof.config import AdapterConfig
from agentproof.models import AssertionOperator, AssertionSpec, RegressionCase
from agentproof.regression import RegressionEngine
from agentproof.subprocess_adapter import AdapterError, SubprocessAdapter

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Tier A adapters are Linux only"
)

AGENT = str(Path(__file__).with_name("hostile_agent.py"))
PYTHON = os.path.realpath(sys.executable)


def make(tmp_path=None, *, extra_argv=(), environ=None, **overrides) -> SubprocessAdapter:
    values = {
        "name": "hostile",
        "tier": "A",
        "argv": (PYTHON, AGENT, *extra_argv),
        "timeout_seconds": 5,
    }
    values.update(overrides)
    return SubprocessAdapter(AdapterConfig(**values), environ=environ if environ is not None else {})


def alive(pid: int) -> bool:
    """True if the process exists and is not a zombie."""
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        return False


def read_pids(path: Path) -> list[int]:
    return [int(x) for x in path.read_text().split()]


def wait_dead(pids: list[int], seconds: float = 3.0) -> list[int]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not any(alive(p) for p in pids):
            return []
        time.sleep(0.05)
    return [p for p in pids if alive(p)]


# ---------------------------------------------------------------- happy path and contract
def test_round_trip_returns_the_json_object():
    adapter = make()
    assert adapter.run({"mode": "ok", "x": [1, 2]}) == {
        "echo": {"mode": "ok", "x": [1, 2]},
        "status": "ok",
    }


def test_metadata_is_recorded_for_a_successful_run():
    adapter = make(env_allow=("A_NAME",), environ={"A_NAME": "value-not-stored"})
    adapter.run({"mode": "ok"})
    meta = adapter.last_metadata
    assert meta is not None
    assert (meta.adapter_name, meta.adapter_tier, meta.exit_code) == ("hostile", "A", 0)
    assert meta.executable_path == PYTHON
    assert meta.executable_sha256 == hashlib.sha256(Path(PYTHON).read_bytes()).hexdigest()
    assert meta.argv == [PYTHON, AGENT]
    assert meta.env_names == ["A_NAME"]
    assert "value-not-stored" not in meta.model_dump_json()
    assert meta.timeout_seconds == 5
    assert meta.stdout_truncated is False and meta.stderr_truncated is False
    assert meta.duration_ms is not None and meta.duration_ms >= 0
    for key in ("RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE", "RLIMIT_NOFILE", "RLIMIT_CORE"):
        assert key in meta.limits


def test_metadata_is_recorded_for_a_failed_run():
    adapter = make()
    with pytest.raises(AdapterError):
        adapter.run({"mode": "exit_nonzero"})
    assert adapter.last_metadata.exit_code == 3


def test_failures_become_failed_results_through_the_engine():
    case = RegressionCase(
        case_id="c1",
        name="hostile",
        input={"mode": "exit_nonzero"},
        assertions=[AssertionSpec(path="status", operator=AssertionOperator.EXISTS)],
    )
    result = RegressionEngine(make()).run_case(case)
    assert result.passed is False
    assert "exit" in (result.error or "").lower()


def test_child_view_is_clean_cwd_group_and_stdin():
    info = make().run({"mode": "info"})
    assert info["stdin_tty"] is False
    assert info["pgid_is_own"] is True
    assert info["cwd"] != os.getcwd()
    assert "agentproof-" in info["cwd"]
    assert not Path(info["cwd"]).exists(), "temp cwd must be deleted after the run"


# ---------------------------------------------------------------- environment
def test_environment_is_empty_plus_allow_list_only():
    parent = {"SECRET_TOKEN": "s3cr3t-value-123456", "OTHER": "x", "ALLOWED": "yes"}
    adapter = make(env_allow=("ALLOWED", "ABSENT"), environ=parent)
    env = adapter.run({"mode": "print_env"})["env"]
    assert env["ALLOWED"] == "yes"
    assert "SECRET_TOKEN" not in env and "OTHER" not in env and "ABSENT" not in env
    assert set(env) <= {"ALLOWED", "PATH", "LC_CTYPE", "LANG", "TMPDIR", "PWD", "SHLVL", "_"}
    assert "s3cr3t" not in json.dumps(env)


def test_real_process_environment_is_not_inherited(monkeypatch):
    monkeypatch.setenv("AGENTPROOF_TEST_SECRET", "must-not-leak-9876543210")
    adapter = SubprocessAdapter(
        AdapterConfig(name="h", tier="A", argv=(PYTHON, AGENT), timeout_seconds=5)
    )  # default environ = os.environ
    out = adapter.run({"mode": "print_env"})
    assert "must-not-leak" not in json.dumps(out)


def test_path_is_fixed_and_not_taken_from_the_parent():
    adapter = make(environ={"PATH": "/tmp/evil"})
    assert "/tmp/evil" not in adapter.run({"mode": "print_env"})["env"].get("PATH", "")


# ---------------------------------------------------------------- timeouts and process groups
def test_infinite_loop_is_killed_by_the_timeout():
    adapter = make(timeout_seconds=1)
    start = time.monotonic()
    with pytest.raises(AdapterError, match="timed out"):
        adapter.run({"mode": "loop"})
    assert time.monotonic() - start < 4


def test_child_that_ignores_sigterm_is_sigkilled():
    adapter = make(timeout_seconds=1)
    start = time.monotonic()
    with pytest.raises(AdapterError, match="timed out"):
        adapter.run({"mode": "ignore_sigterm"})
    assert time.monotonic() - start < 5


def test_whole_process_group_is_killed_on_timeout(tmp_path):
    pid_file = tmp_path / "pids"
    adapter = make(timeout_seconds=1)
    with pytest.raises(AdapterError, match="timed out"):
        adapter.run({"mode": "fork_children", "n": 5, "pid_file": str(pid_file)})
    pids = read_pids(pid_file)
    assert len(pids) == 5
    assert wait_dead(pids) == []


def test_children_left_behind_by_a_normal_exit_are_killed(tmp_path):
    pid_file = tmp_path / "pid"
    adapter = make()
    adapter.run({"mode": "orphan_then_exit", "pid_file": str(pid_file)})
    assert wait_dead(read_pids(pid_file)) == []


def test_sigterm_is_sent_first_so_a_child_can_shut_down_cleanly(tmp_path):
    marker = tmp_path / "term"
    adapter = make(timeout_seconds=1)
    with pytest.raises(AdapterError, match="timed out"):
        adapter.run({"mode": "term_handler", "marker": str(marker)})
    assert marker.read_text() == "got SIGTERM"


def test_slow_trickle_still_hits_the_total_timeout():
    adapter = make(timeout_seconds=1)
    start = time.monotonic()
    with pytest.raises(AdapterError):
        adapter.run({"mode": "trickle"})
    assert time.monotonic() - start < 4


def test_child_that_never_reads_a_huge_stdin_does_not_deadlock():
    adapter = make(extra_argv=("--no-stdin",), timeout_seconds=5)
    start = time.monotonic()
    out = adapter.run({"mode": "ok", "padding": "p" * 900_000})
    assert out == {"status": "ok"}
    assert time.monotonic() - start < 4


def test_huge_input_to_a_child_that_never_reads_cannot_block_the_deadline():
    adapter = make(extra_argv=("--no-stdin-hang",), timeout_seconds=1)
    start = time.monotonic()
    with pytest.raises(AdapterError, match="timed out"):
        adapter.run({"mode": "ok", "padding": "p" * 900_000})
    assert time.monotonic() - start < 4


# ---------------------------------------------------------------- output caps and parsing
def test_stdout_flood_is_cut_off_and_recorded():
    adapter = make(max_stdout_bytes=100_000, timeout_seconds=5)
    start = time.monotonic()
    with pytest.raises(AdapterError, match="stdout exceeded"):
        adapter.run({"mode": "stdout_flood"})
    assert time.monotonic() - start < 4
    assert adapter.last_metadata.stdout_truncated is True


def test_endless_output_without_newline_is_cut_off():
    adapter = make(max_stdout_bytes=50_000, timeout_seconds=5)
    with pytest.raises(AdapterError, match="stdout exceeded"):
        adapter.run({"mode": "endless_no_newline"})


def test_output_exactly_at_the_cap_is_accepted_and_one_over_is_refused():
    probe = make().run({"mode": "huge_string", "size": 10})
    size = len(json.dumps(probe).encode())  # what the agent prints, minus the newline
    assert make(max_stdout_bytes=size + 1).run({"mode": "huge_string", "size": 10}) == probe
    with pytest.raises(AdapterError, match="stdout exceeded"):
        make(max_stdout_bytes=size).run({"mode": "huge_string", "size": 10})


def test_huge_string_over_the_cap_is_refused():
    with pytest.raises(AdapterError, match="stdout exceeded"):
        make().run({"mode": "huge_string", "size": 2_000_000})


def test_stderr_flood_is_truncated_then_killed_and_never_stored_in_full():
    adapter = make(max_stderr_bytes=2_000, timeout_seconds=5)
    start = time.monotonic()
    with pytest.raises(AdapterError, match="stderr flood") as info:
        adapter.run({"mode": "stderr_flood"})
    assert time.monotonic() - start < 3  # killed by the flood rule, not by the 5 s timeout
    assert adapter.last_metadata.stderr_truncated is True
    assert len(str(info.value)) < 2_000


@pytest.mark.parametrize(
    ("mode", "fragment"),
    [
        ("invalid_utf8", "utf-8"),
        ("non_json", "json"),
        ("empty", "json"),
        ("json_array", "object"),
        ("json_scalar", "object"),
        ("deep_json", "json"),
        ("deep_object", "deep"),
        ("nan", "json"),
        ("huge_int", "json"),
        ("exit_nonzero", "exit"),
        ("crash", "signal"),
    ],
)
def test_malformed_output_is_a_failed_result(mode, fragment):
    with pytest.raises(AdapterError) as info:
        make().run({"mode": mode})
    assert fragment in str(info.value).lower()


def test_error_text_is_short_single_line_and_escapes_control_characters():
    with pytest.raises(AdapterError) as info:
        make().run({"mode": "non_json"})
    text = str(info.value)
    assert len(text) < 1_000 and "\n" not in text and "\x1b" not in text


# ---------------------------------------------------------------- resource limits
def test_limits_are_applied_to_the_child():
    limits = make(memory_limit_bytes=256 * 1024 * 1024).run({"mode": "limits"})["limits"]
    assert re.search(r"Max core file size\s+0\s+0", limits)
    assert re.search(r"Max address space\s+268435456\s+268435456", limits)
    assert re.search(r"Max open files\s+64\s+64", limits)
    assert re.search(r"Max file size\s+\d+\s+\d+", limits)


def test_address_space_limit_is_enforced():
    adapter = make(memory_limit_bytes=256 * 1024 * 1024)
    assert adapter.run({"mode": "alloc", "bytes": 1 << 30}) == {"alloc": "denied"}
    assert adapter.run({"mode": "alloc", "bytes": 1 << 20}) == {"alloc": "succeeded", "n": 1 << 20}


def test_file_size_limit_is_enforced():
    assert make().run({"mode": "write_big_file", "bytes": 64 * 1024 * 1024}) == {"write": "denied"}


# ---------------------------------------------------------------- executable checks (fail closed)
def test_missing_executable_is_refused():
    adapter = make(argv=("/definitely/not/here", AGENT))
    with pytest.raises(AdapterError, match="executable"):
        adapter.run({"mode": "ok"})


def test_directory_and_non_executable_are_refused(tmp_path):
    for path in (tmp_path, Path(AGENT)):  # the agent script itself is not executable
        with pytest.raises(AdapterError, match="executable"):
            make(argv=(str(path),)).run({"mode": "ok"})


def test_pinned_hash_must_match():
    good = hashlib.sha256(Path(PYTHON).read_bytes()).hexdigest()
    assert make(executable_sha256=good).run({"mode": "ok"})["status"] == "ok"
    with pytest.raises(AdapterError, match="sha256"):
        make(executable_sha256="0" * 64).run({"mode": "ok"})


def test_hash_change_between_runs_is_refused(tmp_path):
    exe = tmp_path / "agent.sh"
    exe.write_text('#!/bin/sh\necho \'{"v": 1}\'\n')
    exe.chmod(0o755)
    pin = hashlib.sha256(exe.read_bytes()).hexdigest()
    adapter = make(argv=(str(exe),), executable_sha256=pin)
    assert adapter.run({}) == {"v": 1}
    exe.write_text('#!/bin/sh\necho \'{"v": 2}\'\n')
    exe.chmod(0o755)
    with pytest.raises(AdapterError, match="sha256"):
        adapter.run({})


def test_group_or_world_writable_executable_is_refused(tmp_path):
    exe = tmp_path / "agent.sh"
    exe.write_text('#!/bin/sh\necho \'{"v": 1}\'\n')
    exe.chmod(0o757)
    with pytest.raises(AdapterError, match="writable"):
        make(argv=(str(exe),)).run({})


def test_symlinked_executable_is_resolved_and_recorded(tmp_path):
    link = tmp_path / "py"
    link.symlink_to(PYTHON)
    adapter = make(argv=(str(link), AGENT))
    adapter.run({"mode": "ok"})
    assert adapter.last_metadata.executable_path == PYTHON


def test_unsupported_platform_fails_closed(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(AdapterError, match="Linux"):
        make().run({"mode": "ok"})


def test_unexecutable_script_without_shebang_is_a_failed_result(tmp_path):
    exe = tmp_path / "noshebang"
    exe.write_text("echo hi\n")
    exe.chmod(0o755)
    with pytest.raises(AdapterError, match="could not start"):
        make(argv=(str(exe),)).run({})


def test_no_shell_is_involved_argv_items_are_passed_verbatim():
    weird = "; touch /tmp/pwned $(id) `id` | cat"
    info = make(extra_argv=(weird,)).run({"mode": "info"})
    assert info["argv"][-1] == weird
    assert not Path("/tmp/pwned").exists()


# ---------------------------------------------------------------- what Tier A does NOT block
def test_tier_a_does_not_stop_writes_outside_the_temp_dir(tmp_path):
    target = tmp_path / "outside.txt"
    make().run({"mode": "write_outside", "path": str(target)})
    assert target.read_text() == "written by the agent"  # documented: Tier A is not a sandbox


def test_tier_a_does_not_stop_reading_user_files(tmp_path):
    marker = tmp_path / "private.txt"
    marker.write_text("x")
    assert make().run({"mode": "read_home", "path": str(marker)}) == {"can_read": True}


def test_tier_a_does_not_block_the_network():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        port = server.getsockname()[1]
        assert make().run({"mode": "network", "port": port}) == {"connected": True}
    finally:
        server.close()


# ---------------------------------------------------------------- cleanup
def test_symlinks_and_unreadable_dirs_in_cwd_do_not_make_cleanup_follow_or_crash(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "precious.txt").write_text("keep me")
    adapter = make()
    assert adapter.run({"mode": "symlink_trick", "victim": str(victim)}) == {"status": "planted"}
    assert (victim / "precious.txt").read_text() == "keep me"
    assert victim.is_dir()


def test_temp_dirs_do_not_accumulate():
    import tempfile

    before = {p for p in Path(tempfile.gettempdir()).glob("agentproof-*")}
    adapter = make()
    for _ in range(3):
        adapter.run({"mode": "ok"})
    with pytest.raises(AdapterError):
        adapter.run({"mode": "exit_nonzero"})
    after = {p for p in Path(tempfile.gettempdir()).glob("agentproof-*")}
    assert after <= before
