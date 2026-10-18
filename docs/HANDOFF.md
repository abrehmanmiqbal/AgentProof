# Handoff — Read This First

## State (end of session 4, 2026-10-18)
`main` contains: assertion operators `gt`/`lt`/`regex` (D-009), 100-assertion cap, README CLI docs, `examples/`, `run-all --repeat`, oversized-output fix, `docs/THREAT_MODEL.md`, `docs/ADAPTER_ISOLATION.md` (design only). 142 tests passing, `ruff check .` clean, Python 3.12.3 locally. **CI on GitHub was observed passing on 3.11 and 3.12 for 161104d**; check the Actions tab / API for the newest commit first (CI for the session-4 commits was checked at the end of the session, see TEST_EVIDENCE.md).

## Rules
1. Read AGENTS.md and docs/ first; verify the repo rather than trusting notes.
2. `python -m pip install -e ".[dev]" && ruff check . && pytest && agentproof demo` before and after changes.
3. Test-first; record exact commands/results; never fabricate evidence; say what is NOT verified.
4. Traces/cases are untrusted data. **Do NOT write any adapter that executes commands/code or makes network calls until the owner has accepted D-010 (docs/ADAPTER_ISOLATION.md) and answered its four open questions.**
5. Do not publish, spend money, choose a LICENSE, or commit secrets. Push tokens are used inline in one `git push` command only (never saved or printed).

## Known issues / design notes
- Dot-path syntax cannot address keys that contain "." (no escaping yet).
- `contains` follows Python `in` (substring / membership / dict key).
- Run history stores full result JSON; no retention/pruning. No secret redaction (THREAT_MODEL #8).
- `local-legacy` runner is a deliberate demo "bug", not a real agent.
- Regex validation is an estimate-based mitigation, not a proof (D-009); it uses private `re._parser` (fails closed).
- Piping CLI output into `head` prints a `BrokenPipeError` traceback (cosmetic, unfixed).
- Python 3.11 is verified only through GitHub CI, not locally.
- **No LICENSE file: waiting for the owner to choose one.**

## Next concrete tasks (in order)
1. **Owner decisions needed:** (a) which LICENSE (MIT / Apache-2.0 / other) — then add the file; (b) review docs/ADAPTER_ISOLATION.md and answer its 4 questions, then mark D-010 Accepted.
2. Without waiting on the owner: DB migration v2 with run-metadata columns (design step 1 in ADAPTER_ISOLATION.md §8) — also gives the first real v1 -> v2 migration test; or secret-redaction of stored outputs (THREAT_MODEL #8); or CONTRIBUTING.md.
3. After D-010 is accepted: `agentproof.toml` loader, hostile test agent, Tier A subprocess adapter (test-first, Linux only).
