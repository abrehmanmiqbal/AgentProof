# Handoff — Read This First

## State
Session 2 work was pushed to GitHub `main` in session 3 (d5b6852 -> e9e4ac4). Session 3 added the `report` command (55 tests passing, ruff clean, Python 3.12.3). **CI on GitHub has still not been observed** (GitHub API was rate-limited when checked) — look at the Actions tab first.

## Step 0 (session 2 delivery, now done): land the work
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
Reports are done (`report.py`, `agentproof report`). Next: `case delete` and a `run-all` command, `--output` for reports. After that: repeat-run flakiness (`--repeat N`), more assertion operators (numeric `gt/lt`, `regex` with length limit), then adapter-isolation design (D-008).
