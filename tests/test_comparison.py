import pytest

from regressagent.comparison import AssertionChange, Verdict, compare_results, compare_runs
from regressagent.models import AssertionOperator, AssertionSpec, RegressionCase, RegressionResult
from regressagent.regression import RegressionEngine
from regressagent.storage import Repository


def res(passed_map, *, error=None, case_id="c"):
    from regressagent.models import AssertionResult

    return RegressionResult(
        case_id=case_id,
        passed=bool(passed_map) and all(passed_map.values()) and error is None,
        error=error,
        assertions=[
            AssertionResult(path=p, operator=AssertionOperator.EQUALS, passed=ok, message="m")
            for p, ok in passed_map.items()
        ],
    )


def changes(cmp):
    return {d.path: d.change for d in cmp.diffs}


def test_fixed_assertion_is_improved():
    cmp = compare_results(res({"a": False, "b": True}), res({"a": True, "b": True}))
    assert cmp.verdict == Verdict.IMPROVED
    assert changes(cmp) == {"a": AssertionChange.FIXED, "b": AssertionChange.STILL_PASSING}


def test_any_regression_wins_over_improvement():
    cmp = compare_results(res({"a": False, "b": True}), res({"a": True, "b": False}))
    assert cmp.verdict == Verdict.REGRESSED


def test_unchanged_including_still_failing():
    cmp = compare_results(res({"a": False}), res({"a": False}))
    assert cmp.verdict == Verdict.UNCHANGED
    assert changes(cmp)["a"] == AssertionChange.STILL_FAILING


def test_candidate_that_now_errors_is_regression():
    cmp = compare_results(res({"a": True}), res({}, error="Runner raised X"))
    assert cmp.verdict == Verdict.REGRESSED
    assert cmp.after_error == "Runner raised X"
    assert changes(cmp)["a"] == AssertionChange.REMOVED


def test_error_then_pass_is_improved():
    cmp = compare_results(res({}, error="boom"), res({"a": True}))
    assert cmp.verdict == Verdict.IMPROVED


def test_added_assertion_alone_is_unchanged():
    cmp = compare_results(res({"a": True}), res({"a": True, "b": True}))
    assert cmp.verdict == Verdict.UNCHANGED
    assert changes(cmp)["b"] == AssertionChange.ADDED


def test_different_cases_cannot_be_compared():
    with pytest.raises(ValueError):
        compare_results(res({"a": True}, case_id="x"), res({"a": True}, case_id="y"))


def test_end_to_end_failure_to_fix_with_stored_runs():
    """Core loop: failing run saved as baseline -> fix -> rerun -> assertion-based comparison."""

    class Buggy:
        def run(self, i):
            return {"message": "Hi, Ava!", "action": "greet"}

    class Fixed:
        def run(self, i):
            return {"message": "Hello, Ava!", "action": "greet"}

    case = RegressionCase(
        case_id="greet",
        name="greeting",
        input={"action": "greet", "name": "Ava"},
        assertions=[
            AssertionSpec(path="message", operator=AssertionOperator.EQUALS, expected="Hello, Ava!"),
            AssertionSpec(path="action", operator=AssertionOperator.EQUALS, expected="greet"),
        ],
    )
    with Repository() as repo:
        repo.save_case(case)
        r1 = repo.record_run(case, RegressionEngine(Buggy()).run_case(case), label="before", runner_name="buggy")
        r2 = repo.record_run(case, RegressionEngine(Fixed()).run_case(case), label="after", runner_name="fixed")
        cmp = compare_runs(repo.get_run(r1), repo.get_run(r2))
    assert cmp.verdict == Verdict.IMPROVED
    assert cmp.same_case_definition is True
    assert changes(cmp) == {"message": AssertionChange.FIXED, "action": AssertionChange.STILL_PASSING}
