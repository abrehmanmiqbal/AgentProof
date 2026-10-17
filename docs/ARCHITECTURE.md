# Architecture

## Product loop
Capture an agent execution and its observable inputs/outputs → turn a failure into a saved regression case → rerun the case against a candidate implementation → evaluate explicit assertions → produce a reproducible report.

## Initial boundaries
- Core domain: test cases, runs, traces, assertions, results, and reports.
- Runner interface: provider-neutral contract for invoking an agent.
- Local runner: deterministic, offline implementation for reliable demos and tests.
- Persistence: local database behind a repository boundary; migrations must be explicit.
- Interfaces: API and CLI first; UI follows after core workflows are testable.
- Security: traces and imported cases are untrusted data. Never execute arbitrary trace content.

## Proposed implementation direction
Use Python with typed domain models and pytest for the first vertical slice. Choose persistence and API dependencies only after inspecting the environment and documenting the decision. Keep the deterministic local runner independent of external model providers.

## Non-goals for the first slice
- Requiring paid model APIs, hosted infrastructure, or credentials.
- Arbitrary shell/code execution from recorded traces.
- Claiming statistical or semantic reliability from an ungrounded score.
- Public deployment before security and release checks.

This is an initial direction, not a claim that any components have been implemented.
