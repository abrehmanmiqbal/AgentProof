"""Regression tests for defects found when the core was first executed (2026-10-17)."""
from agentproof.assertions import evaluate_assertion
from agentproof.models import AssertionOperator, AssertionSpec, RegressionCase
from agentproof.regression import RegressionEngine


def _spec(path, op=AssertionOperator.EXISTS, expected=None):
    return AssertionSpec(path=path, operator=op, expected=expected)


def test_unicode_digit_path_segment_does_not_crash():
    for segment in ["²", "٣", "①"]:
        result = evaluate_assertion({"a": ["x", "y", "z"]}, _spec(f"a.{segment}"))
        assert result.passed is False


def test_ascii_list_index_still_works():
    assert evaluate_assertion({"a": ["x", "y"]}, _spec("a.1")).passed is True


def test_equals_is_type_strict_for_bool_vs_int():
    eq = AssertionOperator.EQUALS
    assert evaluate_assertion({"a": True}, _spec("a", eq, 1)).passed is False
    assert evaluate_assertion({"a": 1}, _spec("a", eq, True)).passed is False
    assert evaluate_assertion({"a": True}, _spec("a", eq, True)).passed is True


def test_equals_is_strict_inside_nested_structures():
    eq = AssertionOperator.EQUALS
    assert evaluate_assertion({"a": [1, 0]}, _spec("a", eq, [True, False])).passed is False
    assert evaluate_assertion({"a": {"k": [1, {"z": 2}]}}, _spec("a", eq, {"k": [1, {"z": 2}]})).passed


def test_not_equals_uses_same_strict_comparison():
    ne = AssertionOperator.NOT_EQUALS
    assert evaluate_assertion({"a": True}, _spec("a", ne, 1)).passed is True


def test_int_and_float_numeric_equality_is_preserved():
    assert evaluate_assertion({"a": 1}, _spec("a", AssertionOperator.EQUALS, 1.0)).passed is True


class _Exploding:
    def run(self, input_data):
        raise RuntimeError("agent exploded")


def test_runner_exception_becomes_failed_result_not_crash():
    case = RegressionCase(case_id="c", name="n", input={}, assertions=[_spec("x")])
    result = RegressionEngine(_Exploding()).run_case(case)
    assert result.passed is False
    assert result.error is not None and "RuntimeError" in result.error
    assert result.assertions == []


def test_non_dict_runner_output_is_a_failed_result():
    class Bad:
        def run(self, input_data):
            return ["not", "a", "dict"]

    case = RegressionCase(case_id="c", name="n", input={}, assertions=[_spec("x")])
    result = RegressionEngine(Bad()).run_case(case)
    assert result.passed is False
    assert "dict" in result.error
