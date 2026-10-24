"""Provider-neutral runner contract and deterministic offline implementation."""
from __future__ import annotations

from typing import Any, Protocol


class AgentRunner(Protocol):
    """Contract implemented by local or external agent adapters."""

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Run one input and return a JSON-compatible structured output."""
        ...


class DeterministicLocalRunner:
    """Predictable local runner for demos and tests; makes no network calls."""

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        action = input_data.get("action", "echo")

        if action == "greet":
            name = input_data.get("name", "there")
            return {"message": f"Hello, {name}!", "action": "greet"}

        if action == "classify":
            text = input_data.get("text", "")
            category = "empty" if not text else "contains_text"
            return {"category": category, "length": len(text), "action": "classify"}

        if action == "echo":
            return {"echo": input_data, "action": "echo"}

        return {"error": "unsupported_action", "action": action}


class LegacyGreeterRunner(DeterministicLocalRunner):
    """Deliberately 'buggy' deterministic runner: greets with 'Hi' instead of 'Hello'.

    Exists so the failure -> fix -> rerun -> compare loop can be demonstrated and tested
    fully offline (compare runner 'local-legacy' as before vs 'local' as after).
    """

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        output = super().run(input_data)
        if output.get("action") == "greet":
            output = {**output, "message": output["message"].replace("Hello,", "Hi,", 1)}
        return output


RUNNERS: dict[str, type] = {
    "local": DeterministicLocalRunner,
    "local-legacy": LegacyGreeterRunner,
}
