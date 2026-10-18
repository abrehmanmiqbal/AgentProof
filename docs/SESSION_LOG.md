# Session Log

## 2026-10-17 (session 1)
- Repository was empty. Added AGENTS.md, memory docs, and first Python core slice (unexecuted).

## 2026-10-17 (session 2)
- Cloned repo, built venv, ran tests (5/5) and demo (exit 0) — first real execution of the code.
- Probed for defects; found and fixed (test-first) 3 core bugs plus 1 corrupt-DB crash.
- Added SQLite persistence (versioned migrations, hashing, size limits), comparison engine, runner registry (`local`, `local-legacy`), CLI subcommands, ruff in dev/CI.
- Tests: 5 -> 44, all passing on Python 3.12.3. Ruff clean.
- BLOCKED on push: no GitHub credentials. Delivered git bundle + patch series instead.
- Next: reports (Markdown/JSON export), run-all, repeat-run flakiness, adapter isolation design. See HANDOFF.md.

## 2026-10-18 (session 4)
- Step 0: CI on 161104d observed green (3.11 + 3.12) via GitHub API.
- Added `gt`/`lt`/`regex` operators with ReDoS guards (D-009), 100-assertion cap, fuzz script; tests 69 -> 130.
- README CLI documentation + `examples/` (3 cases, runnable script, tests); tests 130 -> 137.
- `run-all --repeat`; oversized-output fix; docs/THREAT_MODEL.md; tests 137 -> 142.
- Adapter-isolation design (docs only) + D-010 proposed; HANDOFF rewritten. LICENSE intentionally NOT added (owner must choose).

## 2026-10-18 (sessions 5 and 6: blocked by environment)
- Session 5 changed nothing in the repo. Session 6 only added these notes.
- Blocker 1: `pip download pydantic` fails with "Name or service not known" (pypi.org is in the proxy NO_PROXY list, so pip connects directly and DNS does not resolve; session 5 saw a proxy 403). No dependencies could be installed, so pytest and `agentproof demo` could NOT be run.
- Blocker 2: GitHub API call with the owner token answered "GitHub access to this repository is not enabled for this session"; `add_repo` with access "push" answered "link your GitHub account". CI status and pushing are not possible. Anonymous `git clone` / `git ls-remote` work.
- Not worked around (no mirrors, proxy and TLS settings untouched). No code written, because it could not be tested.
