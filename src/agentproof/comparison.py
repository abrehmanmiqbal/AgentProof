"""Assertion-level before/after comparison of two runs of the same case.

The verdict is derived only from declared assertions (never from a similarity score):
- REGRESSED : any assertion that passed before now fails (or the run now errors)
- IMPROVED  : nothing regressed and at least one assertion went fail -> pass
- UNCHANGED : every assertion has the same outcome in both runs
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from .models import AssertionOperator, RegressionResult
from .storage import StoredRun


class AssertionChange(StrEnum):
    FIXED = "fixed"
    REGRESSED = "regressed"
    STILL_PASSING = "still_passing"
    STILL_FAILING = "still_failing"
    ADDED = "added"
    REMOVED = "removed"


class Verdict(StrEnum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"


class AssertionDiff(BaseModel):
    path: str
    operator: AssertionOperator
    change: AssertionChange
    before_actual: object = None
    after_actual: object = None


class Comparison(BaseModel):
    case_id: str
    before_run_id: int | None = None
    after_run_id: int | None = None
    same_case_definition: bool | None = None
    verdict: Verdict
    before_error: str | None = None
    after_error: str | None = None
    diffs: list[AssertionDiff]


def _key(r) -> tuple[str, str]:
    return (r.path, r.operator.value)


def compare_results(before: RegressionResult, after: RegressionResult) -> Comparison:
    if before.case_id != after.case_id:
        raise ValueError("Cannot compare results of different cases")

    b = {_key(a): a for a in before.assertions}
    a_ = {_key(a): a for a in after.assertions}
    diffs: list[AssertionDiff] = []

    for key in sorted(set(b) | set(a_)):
        bb, aa = b.get(key), a_.get(key)
        if bb is None:
            change = AssertionChange.ADDED
        elif aa is None:
            change = AssertionChange.REMOVED
        elif bb.passed and aa.passed:
            change = AssertionChange.STILL_PASSING
        elif bb.passed and not aa.passed:
            change = AssertionChange.REGRESSED
        elif not bb.passed and aa.passed:
            change = AssertionChange.FIXED
        else:
            change = AssertionChange.STILL_FAILING
        ref = bb or aa
        diffs.append(
            AssertionDiff(
                path=ref.path,
                operator=ref.operator,
                change=change,
                before_actual=bb.actual if bb else None,
                after_actual=aa.actual if aa else None,
            )
        )

    got_worse = (
        any(d.change == AssertionChange.REGRESSED for d in diffs)
        or (after.error is not None and before.error is None and before.passed)
        or (before.passed and not after.passed)
    )
    got_better = (
        any(d.change == AssertionChange.FIXED for d in diffs)
        or (not before.passed and after.passed)
    )
    if got_worse:
        verdict = Verdict.REGRESSED
    elif got_better:
        verdict = Verdict.IMPROVED
    else:
        verdict = Verdict.UNCHANGED

    return Comparison(
        case_id=before.case_id,
        verdict=verdict,
        before_error=before.error,
        after_error=after.error,
        diffs=diffs,
    )


def compare_runs(before: StoredRun, after: StoredRun) -> Comparison:
    comparison = compare_results(before.result, after.result)
    return comparison.model_copy(
        update={
            "before_run_id": before.run_id,
            "after_run_id": after.run_id,
            "same_case_definition": before.case_hash == after.case_hash,
        }
    )
