"""Run regression cases and aggregate explicit assertion results."""
from __future__ import annotations

from .assertions import evaluate_assertion
from .models import RegressionCase, RegressionResult
from .runner import AgentRunner


class RegressionEngine:
    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    def run_case(self, case: RegressionCase) -> RegressionResult:
        """Run one case. Runner failures are recorded as failed results, never raised."""
        try:
            output = self._runner.run(case.input)
        except Exception as exc:  # noqa: BLE001 - agent code is untrusted; record, don't crash
            return RegressionResult(
                case_id=case.case_id,
                passed=False,
                error=f"Runner raised {type(exc).__name__}: {exc}",
            )
        if not isinstance(output, dict):
            return RegressionResult(
                case_id=case.case_id,
                passed=False,
                error=f"Runner must return a dict, got {type(output).__name__}",
            )
        results = [evaluate_assertion(output, spec) for spec in case.assertions]
        return RegressionResult(
            case_id=case.case_id,
            passed=all(result.passed for result in results),
            output=output,
            assertions=results,
        )
