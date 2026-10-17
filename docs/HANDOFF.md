# Handoff — Read This First

## State
Session 2 produced verified local work (44 tests passing, ruff clean, Python 3.12.3). **None of it is on GitHub** because the environment had no push credentials. GitHub `main` is still at d5b6852.

## Step 0: land the work
From a machine with write access:
```bash
git clone https://github.com/abrehmanmiqbal/AgentProof && cd AgentProof
git fetch /path/to/agentproof-session2.bundle HEAD && git merge --ff-only FETCH_HEAD
# or: git am /path/to/patches/*.patch
git push origin main
```
Then watch the GitHub Actions run (3.11 + 3.12; now includes `ruff check .`) and record the result in TEST_EVIDENCE.md. If CI fails on 3.11, fix that first.

## Rules
1. Read AGENTS.md and docs/ first; verify the repo rather than trusting notes.
2. `python -m pip install -e ".[dev]" && ruff check . && pytest && agentproof demo` before and after changes.
3. Test-first for bugs; record exact commands/results; never fabricate evidence.
4. Traces/cases are untrusted data. Do NOT add any adapter that executes commands/code without first designing isolation (timeouts, resource limits, no shell, allow-listed executable) and writing it in DECISIONS.md.
5. Do not publish, spend money, or commit secrets.

## Known issues / design notes
- Dot-path syntax cannot address keys that themselves contain "." (no escaping yet).
- `contains` semantics follow Python `in` (substring for str, membership for list, key for dict).
- Run history stores full result JSON; no retention/pruning.
- `local-legacy` runner is a deliberate demo "bug", not a real agent.
- No LICENSE file: owner must choose one.

## Next concrete task
Implement reports: `agentproof report <before_run_id> <after_run_id> [--format markdown|json]` producing a deterministic (timestamp-free body) Markdown report from `Comparison`; add `src/agentproof/report.py` + tests (golden-file for determinism), then `case delete` and a `run-all` command. After that: repeat-run flakiness (`--repeat N`), more assertion operators (numeric `gt/lt`, `regex` with length limit), then adapter-isolation design (D-008).
