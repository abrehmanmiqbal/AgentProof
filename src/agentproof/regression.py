"""Run regression cases and aggregate explicit assertion results."""
from __future__ import annotations

from .assertions import evaluate_assertion
from .models import RegressionCase, RegressionResult
from .runner import AgentRunner


class RegressionEngine:
    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    def run_case(self, case: RegressionCase) -> RegressionResult:
        output = self._runner.run(case.input)
        results = [evaluate_assertion(output, spec) for spec in case.assertions]
        return RegressionResult(
            case_id=case.case_id,
            passed=all(result.passed for result in results),
            output=output,
            assertions=results,
        )
