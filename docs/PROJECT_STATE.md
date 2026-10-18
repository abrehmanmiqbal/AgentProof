# Project State

_Last updated: 2026-10-17 (session 3). Everything below marked "verified" was executed in this session; see TEST_EVIDENCE.md for exact commands/output._

## Verified status
- Repository: abrehmanmiqbal/AgentProof. Local clone built and tested on **Python 3.12.3 / Linux** only. Python 3.11 (the declared minimum) was **not available** and is **not verified**; CI (3.11 + 3.12) has **never been observed running**.
- `pytest`: **61 passed**. `ruff check .`: **clean**. `agentproof demo`: exit 0. Black-box CLI loop via the installed `agentproof` binary verified (before fails -> after passes -> verdict `improved`).
- Implemented and tested: typed models; provider-neutral runner protocol + deterministic offline runners (`local`, `local-legacy`); assertion engine (equals/not_equals/contains/exists, dot paths, list indices, type-strict bool/int equality); regression engine (runner exceptions and non-dict output become failed results, never crashes); SQLite persistence (versioned migrations, case content hashes, size limits, parameterized SQL, cascade delete); assertion-level before/after comparison (`improved` / `regressed` / `unchanged`); CLI: `demo`, `case add|list|show`, `run`, `runs`, `compare`, `report` (exit 1 on regression), `case delete --yes`, `run-all`; Markdown/JSON report rendering (`report.py`).
- NOT implemented: HTTP API, UI, report file export / HTML reports, trace import/capture, real-agent adapters (subprocess/HTTP), more assertion operators (regex, numeric compare, JSON-schema), CHANGELOG-level release docs, LICENSE, CONTRIBUTING, threat-model doc.

## Commits
Session 2 work was pushed to GitHub `main` in session 3 (remote head verified with `git ls-remote`: d5b6852 -> e9e4ac4). Session 3 added the `report` command on top.
Session 2 commits: 9d1146a hardening fixes, f3ae004 storage, 6eeb09b comparison, fe75aa6 CLI + corrupt-DB fix, e1827bf ruff dev dep/CI step, lint fixes, docs. Base on GitHub: d5b6852.

## BLOCKER
**`git push` fails: no GitHub credentials in the execution environment** (`fatal: could not read Username for 'https://github.com'`). Nothing from session 2 is on GitHub. Apply the delivered `agentproof-session2.bundle` or the `.patch` series (see HANDOFF.md) from a machine with write access.

## Current milestone
Milestone 1 verified. Milestone 2 core (persistence, rerun, comparison) done locally. Milestone 3 CLI partly done.

## Constraints
- Free-first, offline-capable core; no paid API/hosting/accounts for core features.
- Never claim results not executed; no secrets committed; do not execute traces; do not publish without authorization.
