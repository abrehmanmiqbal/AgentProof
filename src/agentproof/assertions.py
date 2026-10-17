"""Safe, explicit assertions over structured output values."""
from __future__ import annotations

from typing import Any

from .models import AssertionOperator, AssertionResult, AssertionSpec


def _resolve_path(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit():
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
        passed = actual == spec.expected
        message = "Values are equal" if passed else "Values are not equal"
    elif spec.operator == AssertionOperator.NOT_EQUALS:
        passed = actual != spec.expected
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
