# Changelog

User-visible changes are recorded here. This project has not had a software release yet.

## Unreleased
- Added: Tier A subprocess adapter (`agentproof.subprocess_adapter`), NOT a sandbox and not yet reachable from the CLI: timeouts with process-group kill, output caps, empty environment plus allow-list, temp cwd, rlimits, bad output becomes a failed result. Tested against a hostile agent.
- Added: `agentproof.toml` loader (`agentproof.config`, parse and validate only; nothing executes yet). Strict keys, argv lists with absolute executables, mandatory `acknowledge_not_sandboxed = true`, hard limit maxima, env allow-list of names, symlink/permission/size checks. Not wired into the CLI yet.
- Added: best-effort secret redaction of everything stored in run history (outputs, errors, assertion values, adapter metadata); the CLI now prints the stored (redacted) result. Not a guarantee, see docs/THREAT_MODEL.md #8.
- Added: DB schema v2 (nullable run-metadata columns for future adapters), atomic migrations.
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
- Added `run-all --repeat N` (per-case `stable`, top-level `unstable` list; default output unchanged). A runner result over 1,000,000 bytes is now recorded as a failed run (previously the run was lost with exit 2).
- Added docs/THREAT_MODEL.md and docs/ADAPTER_ISOLATION.md (design proposal D-010; no adapter code exists).
- Documentation: README now documents the case format, all operators and limits, every CLI command with exit codes. Added `examples/` (three sample cases and `run_example.sh`, a runnable offline walk-through); tests keep the examples valid.
- Added `scripts/fuzz_regex_safety.py` (manual ReDoS fuzz/timing tool, not part of CI).
- Added LICENSE (MIT, D-011) and CONTRIBUTING.md. D-010 (adapter isolation) accepted with the owner-delegated answers; still design only, no adapter code exists. Docs only: no code or test changes; tests were not run in this session (pip blocked).
- Database schema v2: `runs` gains nullable adapter-metadata columns (adapter name/tier, executable path + SHA-256, argv, env variable *names*, timeout/limits, exit code, duration, stdout/stderr truncation flags). Existing v1 databases are upgraded in place on first open; old runs read back with no metadata. Migrations are now atomic (the version bump is part of the transaction) and a negative `user_version` is refused. No adapter exists yet; nothing writes this metadata outside tests.
- CLI: `run` and `run-all` accept `--adapter NAME --config FILE` (Tier A subprocess adapter). Config path is explicit (never discovered), `--adapter` cannot be combined with `--runner`, runs are recorded as `adapter:NAME` with `RunMetadata`; `ConfigError` maps to exit 2. `--runner` now defaults to `None` and resolves to `local`.
- CI: workflow emits pytest failures as annotations and uses `fail-fast: false`; test helper no longer picks a group/world-writable interpreter as the hostile agent (fixed the red CI).
- Packaging: pyproject now declares `license = "MIT"` (SPDX; build needs setuptools>=77), license-files, classifiers (Alpha, Python 3.11/3.12, POSIX Linux), keywords and project URLs; `twine check` passes. README warns not to `pip install agentproof` (name belongs to another project, D-013). Added tests/test_packaging.py.
