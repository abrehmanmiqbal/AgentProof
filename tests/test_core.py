from regressagent.assertions import evaluate_assertion
from regressagent.models import AssertionOperator, AssertionSpec, RegressionCase
from regressagent.regression import RegressionEngine
from regressagent.runner import DeterministicLocalRunner


def test_local_runner_is_deterministic_and_offline():
    runner = DeterministicLocalRunner()
    payload = {"action": "greet", "name": "Ava"}
    assert runner.run(payload) == runner.run(payload)
    assert runner.run(payload)["message"] == "Hello, Ava!"


def test_nested_path_and_list_index_assertion():
    result = evaluate_assertion(
        {"user": {"roles": ["reader", "admin"]}},
        AssertionSpec(path="user.roles.1", operator=AssertionOperator.EQUALS, expected="admin"),
    )
    assert result.passed is True
    assert result.actual == "admin"


def test_missing_path_fails_without_crashing():
    result = evaluate_assertion(
        {"message": "hello"},
        AssertionSpec(path="user.name", operator=AssertionOperator.EQUALS, expected="Ava"),
    )
    assert result.passed is False
    assert result.actual is None


def test_contains_and_exists_operators():
    output = {"message": "Hello, Ava!", "meta": {"ok": True}}
    assert evaluate_assertion(
        output, AssertionSpec(path="message", operator=AssertionOperator.CONTAINS, expected="Ava")
    ).passed
    assert evaluate_assertion(
        output, AssertionSpec(path="meta.ok", operator=AssertionOperator.EXISTS)
    ).passed


def test_regression_engine_passes_and_reports_failed_assertions():
    case = RegressionCase(
        case_id="greeting-001",
        name="Greet Ava",
        input={"action": "greet", "name": "Ava"},
        assertions=[
            AssertionSpec(path="message", operator=AssertionOperator.EQUALS, expected="Hello, Ava!"),
            AssertionSpec(path="action", operator=AssertionOperator.EQUALS, expected="greet"),
        ],
    )
    result = RegressionEngine(DeterministicLocalRunner()).run_case(case)
    assert result.passed is True
    assert len(result.assertions) == 2

    failing_case = case.model_copy(
        update={"assertions": [
            AssertionSpec(path="message", operator=AssertionOperator.EQUALS, expected="Hi, Ava!")
        ]}
    )
    failed = RegressionEngine(DeterministicLocalRunner()).run_case(failing_case)
    assert failed.passed is False
    assert failed.assertions[0].passed is False
