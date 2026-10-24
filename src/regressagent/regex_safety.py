"""Conservative safety checks for user-supplied regular expressions (ReDoS mitigation).

Python's ``re`` is a backtracking engine with no timeout, and a running match cannot be
interrupted from another thread. So safety here is *preventive*: patterns are rejected at
load time unless a static analysis of the parsed pattern says its worst-case cost is small,
and matched text is capped. Rules (see docs/DECISIONS.md D-009):

* pattern length <= MAX_PATTERN_LENGTH; text length <= MAX_TEXT_LENGTH (checked by caller)
* no backreferences or conditionals
* at most ONE unbounded repeat (``*``, ``+``, ``{n,}``), counting multiplication by any
  enclosing repeat (``(.*a){20}`` counts as 20)
* no variable-width repeat nested inside another variable-width repeat
* no alternation inside a variable-width repeat (``(a|a)*``)
* every repeat count <= MAX_REPEAT_COUNT; nested counts multiply to <= MAX_REPEAT_PRODUCT
* estimated worst-case steps (see ``estimate_cost``) <= MAX_COST

This is NOT a proof of safety (the cost model is an estimate, calibrated by measurement on
CPython 3.12), but it removes the known catastrophic families. It fails closed: if the
interpreter internals used for parsing are unavailable, every regex is rejected.
"""
from __future__ import annotations

import re

try:  # Private-but-stable-since-3.11 modules; fail closed if they are ever removed.
    from re import _constants as _c  # type: ignore[attr-defined]
    from re import _parser as _p  # type: ignore[attr-defined]

    _INTERNALS_OK = True
except ImportError:  # pragma: no cover - depends on future CPython versions
    _INTERNALS_OK = False

MAX_PATTERN_LENGTH = 200
MAX_TEXT_LENGTH = 5_000
MAX_REPEAT_COUNT = 100
MAX_REPEAT_PRODUCT = 10_000
MAX_UNBOUNDED_REPEATS = 1
MAX_COST = 200_000_000  # ~1 s worst case on CPython 3.12, measured by fuzzing (TEST_EVIDENCE.md)


class UnsafeRegexError(ValueError):
    """Raised when a pattern is invalid or too risky to evaluate."""


def _walk(sub, state: dict, outer_count: int, in_variable: bool) -> None:
    for op, av in sub:
        if op in (_c.MAX_REPEAT, _c.MIN_REPEAT, _c.POSSESSIVE_REPEAT):
            low, high, body = av
            unbounded = high == _c.MAXREPEAT
            variable = low != high
            top = low if unbounded else high
            if top > MAX_REPEAT_COUNT:
                raise UnsafeRegexError(f"repeat count above {MAX_REPEAT_COUNT} is not allowed")
            if variable and in_variable:
                raise UnsafeRegexError("variable-width repeat nested in another is not allowed")
            count = outer_count * max(top, 1)
            if count > MAX_REPEAT_PRODUCT:
                raise UnsafeRegexError("nested repeat counts are too large")
            if unbounded:
                state["unbounded"] += outer_count
            elif variable:
                state["bounded_product"] *= (high - low + 1) ** outer_count
            _walk(body, state, count, in_variable or variable)
        elif op in (_c.GROUPREF, _c.GROUPREF_EXISTS):
            raise UnsafeRegexError("backreferences and conditionals are not allowed")
        elif op == _c.BRANCH:
            if in_variable:
                raise UnsafeRegexError("alternation inside a repeat is not allowed")
            for branch in av[1]:
                _walk(branch, state, outer_count, in_variable)
        elif op == _c.SUBPATTERN:
            _walk(av[-1], state, outer_count, in_variable)
        elif op in (_c.ASSERT, _c.ASSERT_NOT):
            _walk(av[1], state, outer_count, in_variable)
        elif op == getattr(_c, "ATOMIC_GROUP", None):
            _walk(av, state, outer_count, in_variable)


def estimate_cost(unbounded: int, bounded_product: int) -> int:
    """Pessimistic step estimate: start positions x backtracking choices of all repeats."""
    return MAX_TEXT_LENGTH * (MAX_TEXT_LENGTH**unbounded) * bounded_product


def validate_pattern(pattern: object) -> str:
    """Return ``pattern`` if it is a safe, valid regex; raise UnsafeRegexError otherwise."""
    if not _INTERNALS_OK:  # pragma: no cover
        raise UnsafeRegexError("regex analysis unavailable on this Python; regex disabled")
    if not isinstance(pattern, str) or not pattern:
        raise UnsafeRegexError("regex pattern must be a non-empty string")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise UnsafeRegexError(f"regex pattern exceeds {MAX_PATTERN_LENGTH} characters")
    try:
        parsed = _p.parse(pattern)
        re.compile(pattern)
    except (re.error, RecursionError, OverflowError) as exc:
        raise UnsafeRegexError(f"invalid regex: {exc}") from exc
    state = {"unbounded": 0, "bounded_product": 1}
    _walk(parsed, state, 1, False)
    if state["unbounded"] > MAX_UNBOUNDED_REPEATS:
        raise UnsafeRegexError("at most one unbounded repeat (*, +, {n,}) is allowed")
    if estimate_cost(state["unbounded"], state["bounded_product"]) > MAX_COST:
        raise UnsafeRegexError("pattern is too expensive to evaluate safely")
    return pattern
