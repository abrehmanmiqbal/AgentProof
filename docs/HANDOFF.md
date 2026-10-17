# Handoff — Read This First

## Current verified state
The repository was initially empty. AGENTS.md and eight docs/ memory files are committed and read back successfully. The initial core package, deterministic runner, assertion evaluator, regression engine, CLI demo, tests, and CI workflow are committed. No tests have been executed yet.

## Rules for the next agent/session
1. Read AGENTS.md and all files in docs/ before coding.
2. Read docs/PROJECT_STATE.md, docs/TASKS.md, and docs/TEST_EVIDENCE.md first for the current status.
3. Verify repository contents rather than trusting this note blindly.
4. Run the test suite and CLI demo in Python 3.11+; inspect CI result if available.
5. Prefer a deterministic offline runner and explicit assertions.
6. Run tests and record exact commands plus real results. Never fabricate evidence.
7. Update state, tasks, decisions, changelog, session log, test evidence, and this handoff before stopping.
8. Do not publish, spend money, expose secrets, or run arbitrary trace content.

## Next concrete task
Run `python -m pip install -e ".[dev]"`, `pytest`, and `agentproof demo`. Fix any actual failures, record results, then implement persistence for saved cases/runs.
