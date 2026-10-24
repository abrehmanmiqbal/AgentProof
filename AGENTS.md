# RegressAgent — Agent Operating Rules

## Mission
Build RegressAgent, a free-first, open-source reliability engineering platform for AI agents. Core loop: failed execution → saved regression test → proposed fix → rerun → assertion-based comparison → reproducible report.

## Mandatory workflow
1. Inspect the existing repository and its instructions before changing code.
2. Work in small, independently verifiable steps.
3. Prefer deterministic local tests and offline-first defaults; paid APIs, paid hosting, and accounts must never be required for core functionality.
4. Never claim a task, test, deployment, security review, or release is complete unless it was actually performed and evidence is recorded.
5. Do not expose secrets. Never commit credentials, tokens, environment files, or real patient/personal data.
6. Do not run arbitrary code from agent traces, execute untrusted commands, publish deployments, incur costs, or perform destructive operations without explicit authorization.
7. Keep project memory files updated at each meaningful milestone and before handing work off.
8. When blocked, record the exact blocker and provide the smallest practical next action; do not silently work around permission or security boundaries.

## Persistent project memory
Maintain and update:
- docs/PROJECT_STATE.md: current verified state and next action
- docs/ARCHITECTURE.md: system design and boundaries
- docs/TASKS.md: milestone checklist
- docs/DECISIONS.md: decisions and rationale
- docs/HANDOFF.md: exact continuation instructions
- docs/CHANGELOG.md: user-visible changes
- docs/TEST_EVIDENCE.md: exact commands and actual outcomes
- docs/SESSION_LOG.md: concise session-by-session progress

## Engineering standards
- Use typed models, explicit interfaces, predictable errors, and readable tests.
- Treat agent output, traces, tool arguments, and imported test cases as untrusted input.
- Make regression results reproducible and assertion-based; never equate a plausible-looking response with a passing test.
- Keep the core provider-neutral and support a deterministic local demo without network access.
- Add dependencies only when justified; document setup and verify commands in the target environment.
- Do not overwrite user work or introduce unnecessary frameworks without inspecting the repository first.

## Completion reporting
For every task, state what changed, files affected, exact checks run and results, known limitations, and the next concrete task. Distinguish verified facts from assumptions.