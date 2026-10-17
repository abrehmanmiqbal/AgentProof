"""Command-line entry point for AgentProof."""
from __future__ import annotations

import argparse
import json

from .models import AssertionOperator, AssertionSpec, RegressionCase
from .regression import RegressionEngine
from .runner import DeterministicLocalRunner


def main() -> int:
    parser = argparse.ArgumentParser(prog="agentproof", description="Run the offline AgentProof demo.")
    parser.add_argument("command", choices=["demo"], help="Command to execute.")
    args = parser.parse_args()

    if args.command == "demo":
        case = RegressionCase(
            case_id="demo-greeting",
            name="Deterministic greeting",
            input={"action": "greet", "name": "AgentProof"},
            assertions=[
                AssertionSpec(
                    path="message",
                    operator=AssertionOperator.EQUALS,
                    expected="Hello, AgentProof!",
                ),
                AssertionSpec(path="action", operator=AssertionOperator.EQUALS, expected="greet"),
            ],
        )
        result = RegressionEngine(DeterministicLocalRunner()).run_case(case)
        print(json.dumps(result.model_dump(mode="json"), indent=2))
        return 0 if result.passed else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
