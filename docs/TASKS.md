# Tasks and Milestones
_[x] = done AND verified by an executed check (see TEST_EVIDENCE.md). Local-only = not yet on GitHub._

## Milestone 0 — Baseline and memory
- [x] Inspect repository; add AGENTS.md and memory docs.
- [x] Record initial repository/tooling facts (Python 3.12.3, pydantic 2.14.1, pytest 8.4.2, ruff 0.17.1).

## Milestone 1 — Deterministic core
- [x] Typed models, runner interface, deterministic runner, assertions, unit tests, demo CLI, CI workflow file.
- [x] Execute tests and record exact evidence (5/5 initially; 61/61 now).
- [x] Fix real defects found: unicode-digit path crash; bool==int false pass; runner exceptions crashing engine.
- [ ] Confirm CI actually passes on GitHub (3.11 and 3.12) — needs push access.
- [ ] Verify on Python 3.11.

## Milestone 2 — Persistence and regression workflow
- [x] SQLite persistence + explicit versioned migrations (stdlib sqlite3; see D-005).
- [x] Save cases and runs (with case hash and result JSON).
- [x] Rerun + assertion-based before/after comparison.
- [x] Tests: persistence across connections, hash stability, history immutability, size limits, injection-like ids, corrupt/newer DB.
- [ ] Persist raw traces (no trace model yet).
- [x] Reports: `report` command renders a deterministic, timestamp-free Markdown/JSON report from two runs to stdout (golden-file + injection tests).
- [ ] Write reports to a file / persist them (`--output`).
- [ ] Migration test with a real v1 -> v2 upgrade once a v2 exists.
- [ ] Flakiness/repeat-run support (run N times, report stability).

## Milestone 3 — API and CLI
- [x] CLI: case add/list/show, run, runs, compare (+ exit codes) with tests.
- [x] CLI: `report <before> <after> [--format markdown|json]` (exit 1 if regressed).
- [x] CLI: `case delete <id> --yes` (refuses without --yes; reports runs deleted) and `run-all --label L [--runner R]` (exit 1 if any fail, exit 2 if no cases).
- [ ] Validated HTTP API (local-only bind by default) + integration tests.
- [ ] Docs for CLI/API usage (README only has install/test right now).

## Milestone 4 — Usable interface
- [ ] Minimal local UI (cases, runs, diffs, reports); empty/error/loading states.

## Milestone 5 — Security and robustness
- [x] Case files: size cap (1,000,000 bytes), JSON-only parse, typed validation, `extra=forbid`; hostile/malformed/deep-nesting/invalid-UTF-8 probes rejected cleanly.
- [ ] Redact secrets in stored outputs; limit assertion count/depth; regex-safety (ReDoS) if regex added.
- [ ] Isolation design for real-agent adapters (subprocess sandboxing, timeouts, resource limits) — required BEFORE any adapter that runs user code/commands.
- [ ] Threat model doc.

## Milestone 6 — Release preparation
- [x] Ruff added to dev extras and CI (verified locally only).
- [ ] LICENSE (needs owner's choice), CONTRIBUTING, examples/ dir with sample case JSON, README CLI docs.
- [ ] Clean-install verification from docs on 3.11 and 3.12.

## Milestone 7 — Distribution readiness
- [ ] Naming/branding availability check; clean-install verification; release notes. Do not publish without authorization.
