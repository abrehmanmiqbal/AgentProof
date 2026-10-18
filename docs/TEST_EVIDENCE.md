# Test Evidence
Only commands actually executed are listed. Environment: Linux container, Python 3.12.3 venv, pydantic 2.14.1, pytest 8.4.2, ruff 0.17.1. Python 3.11: NOT available/NOT tested. GitHub Actions: NOT observed.

## 2026-10-17 (session 1) — baseline
- Repo was empty; AGENTS.md, docs, and first core slice committed via GitHub integration. No code executed.

## 2026-10-17 (session 2)
1. `git clone https://github.com/abrehmanmiqbal/AgentProof` — OK (HEAD d5b6852).
2. `python3 -m venv .venv && pip install -e ".[dev]"` — OK.
3. `pytest` on committed code — **5 passed in 0.10s**.
4. `agentproof demo` on committed code — exit 0, both assertions passed.
5. Edge-case probe script against committed code found 3 defects (all reproduced before fixing):
   - `evaluate_assertion({"a":[...]}, path "a.²")` -> `ValueError` crash (str.isdigit accepts Unicode digits).
   - `equals` with actual `True`, expected `1` -> passed (false positive).
   - Runner raising `RuntimeError` -> exception propagated out of `RegressionEngine.run_case`.
6. Added tests/test_hardening.py first: **6 failed, 7 passed** (expected failures). After fixes: **13 passed**.
7. Added storage + tests: **26 passed**. Added comparison + tests: **34 passed**. Added CLI + tests: **42 passed**.
8. Black-box run of installed `agentproof` binary in a temp dir: `case add` exit 0; `run --runner local-legacy` exit 1 (passed:false, actual "Hi, Ava!"); `run --runner local` exit 0; `compare 1 2` exit 0, verdict `improved`, assertion `message` change `fixed`.
9. Hostile probes via binary: invalid UTF-8 file -> exit 2 clean error; 5000-deep JSON nesting -> exit 2 ("recursion limit exceeded"); compare missing run -> exit 2; non-SQLite file as `--db` -> **raw traceback, exit 1 (real defect)**. Added 2 tests (failed first: 2 failed, 42 passed), fixed in `Repository.__init__`; rerun: exit 2 with message, **44 passed in 0.22s**.
10. `ruff check .` — initially 2 findings (I001 import order; PYI034 `__enter__` return type); fixed; now **All checks passed!**. Final: `pytest` **44 passed in 0.22s**; `agentproof demo` exit 0.
11. `git push origin HEAD:main` — **FAILED: no credentials** (`could not read Username for 'https://github.com'`).
12. Delivery check: bundle of d5b6852..d5eff4f fast-forward-merged onto a fresh clone of GitHub `main`; there `ruff check .` passed, `pytest` **44 passed in 0.31s**, `agentproof demo` exit 0. README "Try the full loop" snippet run as written: add=0, run-before=1, run-after=0, compare verdict `improved`. (A final docs-only commit, this note, was added after that check.)

## 2026-10-17 (session 3)
1. `git bundle list-heads`: bundle was incremental (needs d5b6852); fetched onto fresh clone of GitHub `main`, `git merge --ff-only` OK (7 commits, d5b6852..e9e4ac4). `pytest` **44 passed**, `ruff check .` clean.
2. `git push` with first token — **403** (no write permission); second token — **rejected**: workflow-file change needs `workflow` scope; after the token was fixed — **pushed d5b6852..e9e4ac4**; `git ls-remote origin main` = e9e4ac4 = local HEAD.
3. GitHub Actions status via API: **not obtained** (anonymous API rate limit exceeded).
4. `report` command, test-first: wrote tests/test_report.py + hand-written golden file; first run failed at collection (module missing). After implementing `report.py` + CLI: `pytest` **55 passed in 0.27s**, `ruff check .` clean.
5. Black-box: `case add` / `run --runner local-legacy` (exit 1) / `run --runner local` (exit 0) / `report 1 2` exit 0, output matched the golden shape; two consecutive `report 1 2` outputs were byte-identical (`cmp`).

6. `case delete` + `run-all`, test-first: added 6 tests to tests/test_cli.py; first run **6 failed, 9 passed** (expected: commands missing). After implementing: `pytest` **61 passed in 0.36s**, `ruff check .` clean.
7. Black-box (bash, temp DB): `run-all` with no cases -> exit 2 + clear error; two cases with `--runner local-legacy` -> exit 1 (1 passed, 1 failed, both recorded as runs 1 and 2); `--runner local` -> exit 0; `case delete greet-ava` without `--yes` -> exit 2, nothing deleted; with `--yes` -> exit 0, `runs_deleted: 2`; `case list` -> only `echo-x`.
8. Observed (not fixed, not specific to new code): piping CLI output into `head` closes the pipe and Python prints a `BrokenPipeError` traceback.

9. `report --output/--force` and `run --repeat N`, test-first: added 8 tests; first run **6 failed, 17 passed** (one test, `--repeat` out of range, passed vacuously because argparse rejected the unknown flag). After implementing: `pytest` **69 passed in 0.51s**, `ruff check .` clean.
10. Mutation check: temporarily widened the `--repeat` range check to -5..999 -> `test_run_repeat_out_of_range_is_rejected` **failed** (so it really tests the check); restored, **69 passed**.
11. Black-box (bash, temp DB): `run --repeat 3` -> runs 2,3,4 recorded, `stable: true`, exit 0; `report --output r.md` exit 0 and file written; same command again -> exit 2 ("already exists; use --force"); with `--force` exit 0; nonexistent directory -> exit 2 clean error; `--repeat 99` -> exit 2 ("must be between 1 and 20"). Flaky detection verified only via a test-injected flaky runner (no real nondeterministic agent exists yet).

## Not verified
Python 3.11; CI on GitHub; Windows/macOS; behavior with databases > trivial size; concurrent access to one SQLite file; memory use on near-limit (1 MB) payloads.
