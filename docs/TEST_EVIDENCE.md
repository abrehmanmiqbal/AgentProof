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

## 2026-10-18 (session 4)
Local env: Linux, Python 3.12.3 venv. Python 3.11 not available locally.
1. GitHub API (authenticated, token never printed/stored): latest runs on `main`: 161104d `tests` **completed/success**; jobs `test (3.11)` and `test (3.12)` both success, every step (install, `ruff check .`, `pytest`, `agentproof demo`) success. Earlier commits 3b25690, 2aca26b, e9e4ac4, d5b6852 also success (5 runs listed of 11 total). `git ls-remote origin main` = 161104d.
2. Baseline on fresh clone: `ruff check .` clean, `pytest` **69 passed**.
3. ReDoS measurements (CPython 3.12.3, one `re.search` each, 20 s timeout): `a*a*b` on 2,000 chars 1.84 s; on 5,000 and 10,000 **>20 s**; `a*a*a*b` 300 chars 0.64 s, 600 chars 9.0 s, 1,000 chars >20 s; `(a+)+b` 22 chars 0.40 s; `a*b` 10,000 chars 0.06 s. A first measuring script without per-run timeouts hung and was killed after 300 s.
4. Operators, test-first: tests/test_operators.py written first; first run = collection error (`'gt' is not a valid AssertionOperator`). After implementation: **59 passed, 1 failed**; the failure was a wrong expectation in my test (nested counts 10x10x10x10 = 10,000 equals the cap, not above it); test changed to 5 levels -> `pytest` **129 passed**.
5. Mutation checks on `regex_safety.py`: removing the alternation-in-repeat check -> 2 tests failed (good). Raising `MAX_UNBOUNDED_REPEATS` 1 -> 5 -> **tests still passed** (rule is redundant with the cost cap; documented in D-009).
6. Fuzz (`scripts/fuzz_regex_safety.py`, seed 1234, 3,000 random patterns, adversarial texts, subprocess timeout 30 s): with text cap 10,000 and cost cap 1e9: 577 accepted, slowest **2.77 s**; cost cap 2e8: 494 accepted, slowest 2.45 s (`a+a{2}a{2}^`, cost model underestimates); text cap lowered to 5,000: 570 accepted, slowest **0.81 s** (re-run with the committed script: 0.73 s), **0 timeouts**. This is evidence, not proof.
7. Assertion-count cap, test-first: 1 failed, 60 passed; after change `ruff check .` flagged import order (auto-fixed); final `ruff check .` clean, `pytest` **130 passed**, `agentproof demo` exit 0.
8. Examples, test-first: tests/test_examples.py written first -> **4 failed, 1 skipped** (no examples/ yet). After adding `examples/cases/{greet,classify,echo}.json` + `examples/run_example.sh`: `pytest` **137 passed in 0.92s**, `ruff check .` clean. A test asserts the examples together use every operator in `AssertionOperator`.
9. `./examples/run_example.sh` (bash): script exit 0; before run exit 1, after run exit 0, `compare` verdict `improved`; no stray `agentproof.db` left in the repo.
10. README snippets executed in a temp dir: `case add` 0; `run --runner local-legacy` 1; `run --runner local` 0; `compare 1 2` verdict `improved`; `report 1 2 --output report.md` 0, second time 2 ("already exists; use --force"); `run --repeat 3` -> `total 3`, `stable true`; `run-all` on empty DB -> 2. Also observed: `case add` of an existing id -> exit 2 unless `--overwrite`; `case delete` without `--yes` -> exit 2; unknown case -> exit 2.
11. `run-all --repeat`, test-first: 4 tests added; first run showed 4 failed — 2 genuinely new (`unrecognized arguments: --repeat`) and 2 *old* run-all tests that failed because my new test helper `_two_cases` shadowed an existing helper of the same name (my mistake; renamed `_two_greet_cases`), then **2 failed, 25 passed** (expected). After implementation `pytest` **141 passed**. Mutation: widening `_repeat_count` to -5..999 -> `test_run_repeat_out_of_range_is_rejected` and the new `run-all` range test both **failed**; restored. Black-box: 3 example cases, `run-all --repeat 2` -> total 3, passed 3, unstable [], 2 run_ids per case, exit 0.
12. Probe found a real gap: a runner returning a 2,000,000-char message made `run` exit 2 with "result exceeds 1000000 bytes" and **nothing recorded** (`runs` = []). Test written first (**1 failed, 27 passed**), fix in `cli._run_repeated` (records a failed result with `error`), then `ruff check .` clean, `pytest` **142 passed**.
13. docs/THREAT_MODEL.md written from code facts: `grep` for eval/exec/subprocess/pickle/importlib in `src/` found only `re.compile` (regex_safety); SQL f-strings interpolate only internal constants.
14. Environment probe for the isolation design (python3 + `command -v`): `resource`, `os.killpg`, `tomllib` available; `unshare` present; `bwrap`, `docker`, `podman`, `nsjail`, `firejail` NOT installed. The isolation design (docs/ADAPTER_ISOLATION.md) is **unimplemented and untested**; none of its rlimit/sandbox claims were exercised.

## Not verified
Python 3.11; CI on GitHub; Windows/macOS; behavior with databases > trivial size; concurrent access to one SQLite file; memory use on near-limit (1 MB) payloads.

## 2026-10-18 (session 6, environment blocked)
1. `git ls-remote origin main` = 2c2affd431d8f1bc1e943056af09405206c94ccb = HEAD of a fresh anonymous clone.
2. `ruff check .` (ruff 0.16.8, Python 3.13.16): All checks passed.
3. `pip download pydantic`: FAILED (DNS "Name or service not known" for pypi.org). `python3 -m pytest`: no module named pytest. So the test suite, `agentproof demo` and the session-4 claims (142 tests) were NOT re-run.
4. GitHub API (authenticated): refused by the session ("GitHub access ... not enabled"); `add_repo` push: "link your GitHub account". CI result for commits after 161104d NOT obtained; still missing from this file.

## 2026-10-18 (session 7)
Environment: Linux container, **Python 3.13.16** venv (not 3.12.3 as in session 4), pydantic 2.14.1, pytest 8.4.2, ruff 0.17.1. Python 3.11/3.12 locally: NOT available (CI only).
Step 0:
1. `git ls-remote origin main` = local HEAD = d86dd2e0abded9ad17572e67bff710f4b867ea17.
2. `pip download pydantic`: **works now** (exit 0; pydantic-core 2.50.1 wheel downloaded). The session 5-6 pypi block is gone.
3. GitHub API (unauthenticated GET `/actions/runs`): workflow `tests` **completed/success** for d86dd2e, 1e71429, 2c2affd, 5c2bd95, 7d02442, 05fe3fb, 161104d, 3b25690 (8 most recent runs). Per-job (3.11/3.12) results were NOT inspected this session, only the run-level conclusion.
4. `pip install -e ".[dev]"` OK; `ruff check .` clean; `pytest` **142 passed in 0.80s**; `agentproof demo` exit 0 (both assertions passed); `./examples/run_example.sh` exit 0, `report 1 2` verdict IMPROVED (2 fixed, 1 still passing). So the session-4 claims (142 tests, ruff clean, demo, example) are now re-verified on Python 3.13.16.

Task 1: DB migration v2 + run metadata (test-first):
5. Wrote `tests/test_migration.py` first: collection error (`RunMetadata` missing); after adding only the model: **7 failed, 5 passed** (failures for the right reasons: no v2, no `metadata=` argument). A v1 database is built from a frozen copy of the shipped v1 DDL via raw SQL.
6. Implemented v2 (`ALTER TABLE runs ADD COLUMN` x12, all nullable), `RunMetadata` model, `record_run(..., metadata=)`, `StoredRun.metadata`. Result: `pytest` **161 passed**, `ruff check .` clean. (`tests/test_storage.py` had a hardcoded `== 1` schema-version assertion, updated to 2.)
7. Real defects/weaknesses found while writing the tests: (a) the version bump ran *after* COMMIT, so a crash between them would leave a v2 schema labelled v1 and the next start would re-run `ALTER TABLE` and fail; the bump now runs inside the migration transaction; (b) `PRAGMA user_version = -1` made `range(-1, N)` index `MIGRATIONS[-1]` (it was only refused by accident); now refused explicitly with `StorageError`.
8. Mutation checks (break code, confirm a test fails, restore): removing the negative-version guard -> `test_negative_user_version_is_refused_not_misapplied` failed; moving the bump after COMMIT -> **survived at first** (my rollback test did not cover it), so I added `test_version_bump_happens_inside_the_migration_transaction` (SQLite trace: BEGIN < bump < COMMIT); the mutation is then caught; disabling metadata validation on read -> 6 tampered-metadata tests failed. After each, code restored: `pytest` **161 passed**.
9. Test-bug notes: my first `RunMetadata` test passed `adapter_tier` twice (TypeError), and the trace test compared "BEGIN" to the traced "BEGIN;" (StopIteration); both were mistakes in the tests, not the code, and were fixed in the tests.
NOT verified: migration of a large v1 database (only 1 case / 2 runs used); concurrent opening of a v1 file by two processes while it migrates.

Task 2: secret redaction (session 7, continued):
10. `ruff check .` initially reported 1 finding (RUF007: `zip(parts, parts[1:])`); replaced with `itertools.pairwise`; then `ruff check .`: All checks passed; `pytest`: **227 passed in 2.49s** (Python 3.13.16, ruff 0.17.1).
11. Mutation checks on `redaction.py` (break, run `pytest -x`, restore): skip env-secret replacement, drop token regex, drop URL-password regex, drop sensitive-key forcing, env min length 8 -> 1, disable depth guard: each made **1 test fail**; file restored, 227 passed. (The depth-guard mutant took 74 s to fail.)
NOT verified: CI for the commit containing redaction (checked after push, see below); redaction against real provider output formats beyond the patterns tested; Python 3.11/3.12 locally.

Task 3a: config loader (session 7, continued):
12. `tests/test_config.py` written first: `pytest` failed at collection (no `agentproof.config`). After implementing `config.py`: 79 passed; `ruff check .` initially flagged 1 style finding in the test (UP012), fixed. Full suite: **306 passed in 2.72s**, ruff clean.
13. Mutation checks (break, run tests/test_config.py, restore): ack not required -> 6 failed; ack truthy -> 4; no O_NOFOLLOW -> 1; no writable-permission check -> 2; no normpath check -> 1; forbidden env names off -> 5; no timeout max -> 1; builtin-shadow check off -> 2; tier-B refusal off -> survived (only the message changed), test tightened, then 1 failed. Pre-read size check removed -> survived: equivalent mutant, the same cap is enforced after reading (defence in depth), so oversized files are still refused.
NOT verified: config loading on non-Linux platforms; ownership check with a non-root uid (tests ran as root); behaviour with FIFO or device paths (O_NONBLOCK + S_ISREG refuse them, but this has no test).
