"""Best-effort secret redaction for data RegressAgent *stores* (THREAT_MODEL #8).

This is a safety net, NOT a guarantee. It removes things that are recognisably secrets:
- values of environment variables whose NAME looks secret (TOKEN, SECRET, PASSWORD, ... or ending
  in KEY), when the value is at least 8 characters (shorter values would mangle ordinary text);
- well-known token formats (GitHub, AWS access key id, ``sk-`` style API keys, Slack, Google API
  keys, JWTs, PEM private keys, ``Bearer`` tokens, passwords inside URLs);
- ``name=value`` / ``"name": "value"`` assignments whose name is secret-like (password, token,
  api key, client secret, authorization, ...), value of at least 4 characters;
- every scalar under a secret-named key of a structured value (any length, any type).

It deliberately does NOT detect: secrets without a recognisable shape or name, encoded or
transformed secrets (base64, URL-encoding, reversed, split across fields or by invisible
characters), personal data, or anything shorter than the thresholds above. Redaction applies to
what is written to the database; the case file itself is stored as given. Removing a secret can
make two different secrets look identical in a stored result.

Safety properties kept on purpose: every pattern is anchored with a boundary lookbehind and uses
bounded or single-pass character classes, so hostile 1 MB outputs cannot trigger quadratic
backtracking (timed in tests); structures that are too deep or of unsupported type are replaced
by a marker (fail closed) instead of being stored unscanned; redacting twice equals redacting once.
"""
from __future__ import annotations

import itertools
import os
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .models import RegressionResult

MAX_DEPTH = 64
MIN_ENV_SECRET_LENGTH = 8
MAX_ENV_SECRETS = 200

REDACTED = "[REDACTED]"
_ENV_MARKER = "[REDACTED:env]"
_TOKEN_MARKER = "[REDACTED:token]"
_UNSUPPORTED = "[REDACTED:unsupported-type]"
_TOO_DEEP = "[REDACTED:too-deep]"
_ARGUMENT = "[REDACTED:argument]"

# --- text patterns (applied in order; each replacement is itself stable under re-application) ---
_PEM = re.compile(
    r"-----BEGIN [A-Z ]{0,30}PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]{0,30}PRIVATE KEY-----|\Z)"
)
_TOKENS = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"gh[pousr]_[A-Za-z0-9]{30,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])"
    r"|sk-[A-Za-z0-9_-]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z_-]{35}(?![0-9A-Za-z_-])"
    r"|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r")"
)
_BEARER = re.compile(r"(?i)(?<![A-Za-z0-9])(bearer[ \t]{1,5})[A-Za-z0-9._~+/=-]{16,}")
_URL_PASSWORD = re.compile(r"(?<=://)([^\s/:@]{1,100}):([^\s/@]{1,200})@")
_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    r"((?:password|passwd|secret|token|api[_-]?key|access[_-]?key|secret[_-]?key|private[_-]?key"
    r"|client[_-]?secret|authorization|credentials?)"
    r"[\"']?[ \t]{0,5}[:=][ \t]{0,5}[\"']?)"
    r"(?:(?:basic|bearer|digest|token)[ \t]{1,5})?+"
    r"(?!\[REDACTED)"
    r"[^\s\"',;&]{4,}"
)

# --- key names whose values are always redacted in structured data ---
_SENSITIVE_KEY_SUFFIXES = (
    "password", "passwd", "secret", "token", "apikey", "accesskey", "secretkey", "privatekey",
    "authorization", "credential", "credentials",
)
_SENSITIVE_ENV_WORDS = {
    "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "CREDENTIALS", "APIKEY", "PRIVATEKEY",
    "ACCESSKEY", "SECRETKEY",
}
_SENSITIVE_ENV_PAIRS = {("API", "KEY"), ("PRIVATE", "KEY"), ("ACCESS", "KEY"), ("SECRET", "KEY")}


def _squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_sensitive_key(name: str) -> bool:
    """True for names like ``password``, ``apiKey``, ``x-api-key``, ``id_token``; False for
    ``token_count``, ``max_tokens``, ``author``."""
    return _squash(name).endswith(_SENSITIVE_KEY_SUFFIXES)


def is_sensitive_env_name(name: str) -> bool:
    parts = name.upper().split("_")
    if parts[-1] == "KEY" or any(p in _SENSITIVE_ENV_WORDS for p in parts):
        return True
    return any(pair in _SENSITIVE_ENV_PAIRS for pair in itertools.pairwise(parts))


class Redactor:
    """Redacts secrets from text and JSON-like values. Create one per use; it is cheap."""

    def __init__(
        self, environ: Mapping[str, str] | None = None, extra_secrets: Iterable[str] = ()
    ) -> None:
        candidates = set(extra_secrets)
        for name, value in (environ or {}).items():
            if is_sensitive_env_name(name):
                candidates.add(value)
        usable = {
            v for v in candidates
            if isinstance(v, str) and len(v) >= MIN_ENV_SECRET_LENGTH and "REDACTED" not in v
        }
        # Longest first so a secret that contains another one is replaced as a whole.
        self._secrets = sorted(usable, key=len, reverse=True)[:MAX_ENV_SECRETS]

    @classmethod
    def from_environ(cls) -> Redactor:
        return cls(environ=os.environ)

    # ---- text ----
    def text(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, _ENV_MARKER)
        text = _PEM.sub("[REDACTED:private-key]", text)
        text = _TOKENS.sub(_TOKEN_MARKER, text)
        text = _BEARER.sub(lambda m: m.group(1) + _TOKEN_MARKER, text)
        text = _URL_PASSWORD.sub(lambda m: f"{m.group(1)}:[REDACTED:url-password]@", text)
        return _ASSIGNMENT.sub(lambda m: m.group(1) + "[REDACTED:assignment]", text)

    # ---- structured values ----
    def value(self, data: Any) -> Any:
        """Return a redacted copy of a JSON-like value (never mutates the input)."""
        return self._walk(data, 0, False)

    def _walk(self, data: Any, depth: int, force: bool) -> Any:
        if depth > MAX_DEPTH:
            return _TOO_DEEP
        if data is None or isinstance(data, bool):
            return data
        if isinstance(data, str):
            return REDACTED if force else self.text(data)
        if isinstance(data, int | float):
            return REDACTED if force else data
        if isinstance(data, list | tuple):
            return [self._walk(item, depth + 1, force) for item in data]
        if isinstance(data, dict):
            out: dict[str, Any] = {}
            for key, item in data.items():
                skey = key if isinstance(key, str) else str(key)
                new_key = self.text(skey)
                candidate, n = new_key, 1
                while candidate in out:  # two keys redacted to the same text must both survive
                    n += 1
                    candidate = f"{new_key}#{n}"
                out[candidate] = self._walk(item, depth + 1, force or is_sensitive_key(skey))
            return out
        return _UNSUPPORTED

    # ---- domain objects ----
    def result(self, result: RegressionResult) -> RegressionResult:
        """Redact a result's values; verdicts, ids, paths and operators are never altered."""
        data = result.model_dump(mode="json")
        data["output"] = self._walk(data["output"], 1, False)
        if data["error"] is not None:
            data["error"] = self.text(data["error"])
        for assertion in data["assertions"]:
            force = is_sensitive_key(assertion["path"].rsplit(".", 1)[-1])
            assertion["expected"] = self._walk(assertion["expected"], 1, force)
            assertion["actual"] = self._walk(assertion["actual"], 1, force)
        return RegressionResult.model_validate(data)

    def argv(self, argv: list[str]) -> list[str]:
        """Redact a command line: secret-looking items, and the value after ``--token`` style
        flags. Output has the same length as the input."""
        out: list[str] = []
        redact_next = False
        for item in argv:
            if redact_next:
                out.append(_ARGUMENT)
                redact_next = False
                continue
            out.append(self.text(item))
            if item.startswith("-") and "=" not in item and is_sensitive_key(item.lstrip("-")):
                redact_next = True
        return out
