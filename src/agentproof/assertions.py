"""Safe, explicit assertions over structured output values."""
from __future__ import annotations

import re
from typing import Any

from .models import AssertionOperator, AssertionResult, AssertionSpec

_INDEX_RE = re.compile(r"[0-9]+")


def _strict_equal(a: Any, b: Any) -> bool:
    """Equality that never conflates bool with int (True != 1), recursively.

    int and float still compare numerically (1 == 1.0).
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_strict_equal(x, y) for x, y in zip(a, b))
    return a == b


def _resolve_path(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and _INDEX_RE.fullmatch(segment):
            index = int(segment)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def evaluate_assertion(output: dict[str, Any], spec: AssertionSpec) -> AssertionResult:
    exists, actual = _resolve_path(output, spec.path)

    if spec.operator == AssertionOperator.EXISTS:
        passed = exists
        message = "Path exists" if passed else "Path does not exist"
    elif not exists:
        passed = False
        message = f"Path '{spec.path}' does not exist"
    elif spec.operator == AssertionOperator.EQUALS:
        passed = _strict_equal(actual, spec.expected)
        message = "Values are equal" if passed else "Values are not equal"
    elif spec.operator == AssertionOperator.NOT_EQUALS:
        passed = not _strict_equal(actual, spec.expected)
        message = "Values differ" if passed else "Values unexpectedly match"
    elif spec.operator == AssertionOperator.CONTAINS:
        try:
            passed = spec.expected in actual
        except (TypeError, AttributeError):
            passed = False
        message = "Expected value is contained" if passed else "Expected value is not contained"
    else:
        passed = False
        message = f"Unsupported operator: {spec.operator}"

    return AssertionResult(
        path=spec.path,
        operator=spec.operator,
        passed=passed,
        expected=spec.expected,
        actual=actual if exists else None,
        message=message,
    )
