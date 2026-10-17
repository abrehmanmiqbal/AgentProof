# Test Evidence

## 2026-10-17 — Repository baseline
- Action: inspected repository through GitHub integration.
- Finding: repository was initially empty.
- Change: AGENTS.md and eight project-memory documents were committed; all nine were read back successfully through GitHub.
- Core code committed: Pydantic domain models, deterministic local runner, assertion evaluator, regression engine, CLI demo, pytest test file, packaging metadata, and GitHub Actions workflow.
- Local tests: NOT RUN — this session has not executed the repository in a Python environment.
- CI status: NOT checked/verified; workflow was added but no successful run has been confirmed.
- Build status: NOT run.
- Next: execute `python -m pip install -e ".[dev]"`, `pytest`, and `agentproof demo` in a Python 3.11+ environment; record actual output before claiming success.
