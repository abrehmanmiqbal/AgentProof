# Changelog

User-visible changes are recorded here. This project has not had a software release yet.

## Unreleased
- Added AGENTS.md with operating rules, security guardrails, memory-file requirements, and truthful completion reporting.
- Added initial project planning and architecture memory documents.
- Added the first Python core: typed models, deterministic offline runner, assertion evaluation, regression engine, and demo CLI.
- Added pytest coverage, packaging metadata, and a GitHub Actions test workflow. These have not yet been executed/verified in this session.
- Fixed: path segments such as "²" crashed assertion evaluation; `equals` no longer treats `True` as `1`; runner exceptions are recorded as failed results.
- Added: SQLite persistence (cases, runs, content hashes, versioned migrations), before/after comparison with `improved/regressed/unchanged` verdicts, `local-legacy` demo runner.
- Added CLI: `case add|list|show`, `run`, `runs`, `compare` (exit 1 on regression). Corrupt DB files give a clear error (exit 2).
- Added ruff to dev dependencies and CI.
- Added `agentproof report <before_run_id> <after_run_id> [--format markdown|json]`: deterministic, timestamp-free report from a comparison; untrusted values are length-limited and escaped. Exits 1 on regression.
- Added `agentproof case delete <id> --yes` (deletes the case and its runs; refuses without `--yes`) and `agentproof run-all --label L [--runner R]` (runs and records every saved case; exit 1 if any fail, exit 2 if there are no cases).
- Added `agentproof report --output PATH [--force]` (refuses to overwrite an existing file without `--force`) and `agentproof run --repeat N` (1-20; records each run, reports `stable` when every repeat had identical per-assertion outcomes; exit 1 if any repeat failed). Default `run` output is unchanged.
- Added assertion operators `gt` / `lt` (finite numbers only; bool/str actuals fail) and `regex` (`re.search`; restricted patterns, see D-009: max 200 chars, no backreferences, no nested/ambiguous repeats, text capped at 5,000 chars). Unsafe patterns are rejected when a case is loaded. Cases are limited to 100 assertions.
- Added `scripts/fuzz_regex_safety.py` (manual ReDoS fuzz/timing tool, not part of CI).
