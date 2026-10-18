"""Loader for the local, user-authored ``agentproof.toml`` (D-010, ADAPTER_ISOLATION.md s2/s8).

This module only *parses and validates*. It never executes anything, never opens or hashes the
executables it names, and never contacts the network: existence, realpath and SHA-256 checks
belong to the adapter at run time. Commands live here and nowhere else: case files, traces and
the database never contain commands, URLs or environment values.

Safety properties:
- the file is opened without following symlinks, must be a regular file owned by the current
  user or root, must not be group/world writable, and is size-capped before it is parsed;
- unknown keys are errors (no silent typos, no smuggled options);
- ``argv`` is an explicit list (never a string a shell could split) with an absolute,
  normalised executable path;
- every adapter entry must carry ``acknowledge_not_sandboxed = true`` (Tier A is NOT a sandbox);
- limits cannot exceed hard maxima; environment allow-list holds plain *names* only, and names
  that change how programs load code (``LD_*``, ``PYTHON*``, ``PATH`` ...) are refused;
- error messages never echo argv values (they may contain secrets).
"""
from __future__ import annotations

import errno
import math
import os
import posixpath
import re
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .runner import RUNNERS

MAX_CONFIG_BYTES = 64 * 1024
MAX_ADAPTERS = 64
MAX_ARGV_ITEMS = 64
MAX_ARGV_ITEM_LENGTH = 4096
MAX_ENV_ALLOW = 32

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
DEFAULT_MAX_STDOUT_BYTES = 1_000_000
MAX_STDOUT_BYTES = 1_000_000  # matches the storage cap per stored result
DEFAULT_MAX_STDERR_BYTES = 64 * 1024
MAX_STDERR_BYTES = 1_000_000
DEFAULT_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
MIN_MEMORY_LIMIT_BYTES = 16 * 1024 * 1024
MAX_MEMORY_LIMIT_BYTES = 16 * 1024**3

_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TOP_KEYS = {"adapters"}
_ADAPTER_KEYS = {
    "tier", "argv", "acknowledge_not_sandboxed", "timeout_seconds", "max_stdout_bytes",
    "max_stderr_bytes", "memory_limit_bytes", "env_allow", "executable_sha256",
}
_FORBIDDEN_ENV_NAMES = {
    "PATH", "IFS", "ENV", "BASH_ENV", "PERL5OPT", "PERL5LIB", "RUBYOPT", "RUBYLIB",
    "NODE_OPTIONS", "NODE_PATH", "CLASSPATH", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS",
}
_FORBIDDEN_ENV_PREFIXES = ("LD_", "DYLD_", "PYTHON")


class ConfigError(Exception):
    """A predictable, user-facing configuration problem (CLI maps it to exit code 2)."""


@dataclass(frozen=True)
class AdapterConfig:
    name: str
    tier: str
    argv: tuple[str, ...]
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_stdout_bytes: int = DEFAULT_MAX_STDOUT_BYTES
    max_stderr_bytes: int = DEFAULT_MAX_STDERR_BYTES
    memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES
    env_allow: tuple[str, ...] = ()
    executable_sha256: str | None = None


@dataclass(frozen=True)
class Config:
    adapters: Mapping[str, AdapterConfig]


def load_config(path: str | os.PathLike[str]) -> Config:
    """Read, parse and validate a config file. Raises ``ConfigError`` on any problem."""
    text = _read_checked(os.fspath(path))
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML: {exc}") from None
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"unknown top-level key(s): {_names(unknown)}")
    table = data.get("adapters", {})
    if not isinstance(table, dict):
        raise ConfigError("'adapters' must be a table of adapter entries")
    if len(table) > MAX_ADAPTERS:
        raise ConfigError(f"at most {MAX_ADAPTERS} adapters are allowed")
    adapters = {name: _parse_adapter(name, entry) for name, entry in table.items()}
    return Config(adapters=MappingProxyType(adapters))


def _names(keys: set[str]) -> str:
    return ", ".join(repr(k[:40]) for k in sorted(keys)[:5])


def _read_checked(path: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise ConfigError("config file not found") from None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ConfigError("config file is a symlink; refusing to follow it") from None
        raise ConfigError(f"cannot read config file ({exc.strerror})") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ConfigError("config path is not a regular file")
        if info.st_mode & 0o022:
            raise ConfigError("config file must not be writable by group or others")
        if hasattr(os, "geteuid") and info.st_uid not in (0, os.geteuid()):
            raise ConfigError("config file must be owned by you or root")
        if info.st_size > MAX_CONFIG_BYTES:
            raise ConfigError(f"config file is too large (limit {MAX_CONFIG_BYTES} bytes)")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_CONFIG_BYTES + 1)
    except OSError as exc:
        raise ConfigError(f"cannot read config file ({exc.strerror})") from None
    finally:
        os.close(fd)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ConfigError(f"config file is too large (limit {MAX_CONFIG_BYTES} bytes)")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError("config file is not valid UTF-8") from None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _bounded_int(entry: dict[str, Any], key: str, default: int, low: int, high: int, who: str) -> int:
    value = entry.get(key, default)
    if not _is_int(value) or not low <= value <= high:
        raise ConfigError(f"adapter {who}: {key} must be an integer from {low} to {high}")
    return value


def _parse_adapter(name: str, entry: Any) -> AdapterConfig:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ConfigError(
            f"invalid adapter name {name[:40]!r}: use 1-64 chars of a-z, 0-9, '_' or '-', "
            "starting with a letter or digit"
        )
    if name in RUNNERS:
        raise ConfigError(f"adapter name {name!r} would shadow a built-in runner")
    if not isinstance(entry, dict):
        raise ConfigError(f"adapter {name}: entry must be a table")
    unknown = set(entry) - _ADAPTER_KEYS
    if unknown:
        raise ConfigError(f"adapter {name}: unknown key(s): {_names(unknown)}")

    if entry.get("acknowledge_not_sandboxed") is not True:
        raise ConfigError(
            f"adapter {name}: acknowledge_not_sandboxed = true is required. Tier A adapters run "
            "the command as you, with your files and network; use them for trusted code only"
        )
    tier = entry.get("tier")
    if tier == "B":
        raise ConfigError(f"adapter {name}: tier B (sandbox) is not implemented yet")
    if tier != "A":
        raise ConfigError(f"adapter {name}: tier must be \"A\"")

    argv = _parse_argv(name, entry.get("argv"))

    timeout = entry.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int | float)
        or not math.isfinite(timeout)
        or not 0 < timeout <= MAX_TIMEOUT_SECONDS
    ):
        raise ConfigError(
            f"adapter {name}: timeout_seconds must be a number above 0 and at most "
            f"{MAX_TIMEOUT_SECONDS}"
        )

    return AdapterConfig(
        name=name,
        tier="A",
        argv=argv,
        timeout_seconds=timeout,
        max_stdout_bytes=_bounded_int(
            entry, "max_stdout_bytes", DEFAULT_MAX_STDOUT_BYTES, 1, MAX_STDOUT_BYTES, name
        ),
        max_stderr_bytes=_bounded_int(
            entry, "max_stderr_bytes", DEFAULT_MAX_STDERR_BYTES, 1, MAX_STDERR_BYTES, name
        ),
        memory_limit_bytes=_bounded_int(
            entry, "memory_limit_bytes", DEFAULT_MEMORY_LIMIT_BYTES,
            MIN_MEMORY_LIMIT_BYTES, MAX_MEMORY_LIMIT_BYTES, name,
        ),
        env_allow=_parse_env_allow(name, entry.get("env_allow", [])),
        executable_sha256=_parse_sha(name, entry.get("executable_sha256")),
    )


def _parse_argv(name: str, argv: Any) -> tuple[str, ...]:
    if not isinstance(argv, list) or not 1 <= len(argv) <= MAX_ARGV_ITEMS:
        raise ConfigError(
            f"adapter {name}: argv must be a list of 1-{MAX_ARGV_ITEMS} strings "
            "(a single command string is never accepted: no shell)"
        )
    for index, item in enumerate(argv):
        if not isinstance(item, str) or not 1 <= len(item) <= MAX_ARGV_ITEM_LENGTH:
            raise ConfigError(
                f"adapter {name}: argv[{index}] must be a non-empty string of at most "
                f"{MAX_ARGV_ITEM_LENGTH} characters"
            )
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in item):
            raise ConfigError(f"adapter {name}: argv[{index}] contains a control character")
    exe = argv[0]
    if (
        not exe.startswith("/")
        or any(ch.isspace() for ch in exe)
        or posixpath.normpath(exe) != exe
    ):
        raise ConfigError(
            f"adapter {name}: argv[0] must be an absolute, normalised path without spaces "
            "(no '..', no '//', no trailing '/')"
        )
    return tuple(argv)


def _parse_env_allow(name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_ENV_ALLOW:
        raise ConfigError(f"adapter {name}: env_allow must be a list of at most {MAX_ENV_ALLOW} names")
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not _ENV_NAME.fullmatch(item):
            raise ConfigError(f"adapter {name}: env_allow entries must be plain variable names")
        upper = item.upper()
        if upper in _FORBIDDEN_ENV_NAMES or upper.startswith(_FORBIDDEN_ENV_PREFIXES):
            raise ConfigError(
                f"adapter {name}: env_allow may not include {item!r} (it changes how programs "
                "find or load code)"
            )
        if item in seen:
            raise ConfigError(f"adapter {name}: duplicate env_allow entry {item!r}")
        seen.add(item)
    return tuple(value)


def _parse_sha(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ConfigError(f"adapter {name}: executable_sha256 must be 64 lowercase hex characters")
    return value
