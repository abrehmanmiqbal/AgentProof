# Architecture Decision Log

## D-001: Offline deterministic core
**Status:** Accepted  
**Decision:** The core demo and tests must work without paid APIs, accounts, or hosted services.  
**Reason:** Free-first accessibility and reproducibility.

## D-002: Provider-neutral runner boundary
**Status:** Accepted  
**Decision:** External model integrations must sit behind a narrow runner interface.  
**Reason:** Avoid provider lock-in and keep the test engine independently testable.

## D-003: Explicit assertions over vague scores
**Status:** Accepted  
**Decision:** A regression passes or fails based on declared, inspectable assertions; any aggregate score must be explainable.  
**Reason:** Results should be reproducible and auditable.

## D-004: Do not execute imported traces
**Status:** Accepted  
**Decision:** Recorded traces and test fixtures are data, not executable instructions.  
**Reason:** Reduce code-execution and prompt/tool injection risk.

## D-005: Delay framework lock-in until environment inspection
**Status:** Resolved (session 2)  
**Decision:** Keep the dependency set minimal: pydantic only at runtime; persistence uses stdlib `sqlite3`; no web framework yet. Revisit when the HTTP API is built.  
**Reason:** Avoid unnecessary complexity and unsupported assumptions.

## D-006: Type-strict equality for assertions
**Status:** Accepted  
**Decision:** `equals`/`not_equals` never equate bool with int (True != 1), recursively; int/float still compare numerically.  
**Reason:** Python's `True == 1` produced false passes, violating D-003.

## D-007: Runner failures are results, not exceptions
**Status:** Accepted  
**Decision:** Runner exceptions and non-dict output are recorded as failed `RegressionResult` with `error` set.  
**Reason:** Agent code is untrusted/unreliable; a crash must be a persisted, comparable failure.

## D-008: Persistence design
**Status:** Accepted  
**Decision:** SQLite with ordered append-only migrations via `PRAGMA user_version`; refuse newer schemas; runs store the SHA-256 of the exact case JSON; 1,000,000-byte cap per stored case/result.  
**Reason:** Reproducibility, safe upgrades, bounded storage. Note: adapter-isolation design remains an open decision and must precede any adapter that executes code.

## D-009: Regex assertions are restricted and fail closed (ReDoS)
**Status:** Accepted (session 4)  
**Decision:** `regex` uses `re.search`. Patterns are validated when the `AssertionSpec` is built (so `case add` rejects them): max 200 chars; no backreferences/conditionals; at most one unbounded repeat (`*`, `+`, `{n,}`, counted through enclosing fixed repeats); no variable-width repeat inside another; no alternation inside a variable repeat; repeat counts <= 100 (nested product <= 10,000); estimated cost <= 2e8 steps. Matched text must be <= 5,000 chars, otherwise the assertion fails with a clear message (never truncated). `gt`/`lt` require a finite non-bool number for `expected` and a non-bool number as actual. A case may have at most 100 assertions.  
**Reason:** CPython `re` backtracks and cannot be interrupted, so safety must be preventive. Measured on 3.12.3: `a*a*b` on 2,000 chars took 1.8 s and >20 s on 5,000; `(a+)+b` is exponential. Fuzzing 570 accepted patterns against adversarial 5,000-char texts: slowest 0.73-0.81 s, none >30 s.  
**Limits / trade-offs:** Not a proof. The cost model is an estimate; it rejects some legitimate patterns (e.g. `\w+@\w+\.\w+`, `(foo|bar)+`). The "max 1 unbounded repeat" rule is redundant with the cost cap (mutation check showed tests pass without it); kept as an explicit defense. Parsing uses `re._parser`/`re._constants` (private, present in 3.11 and 3.12); if unavailable, regex is rejected entirely. A hard guarantee would need a linear-time engine (e.g. RE2) or a killable worker process; revisit with the adapter-isolation work.

## D-010: Adapter isolation design
**Status:** ACCEPTED 2026-10-18 (owner delegated the answers to the agent in chat: "jo best approach ho woh karo"; the owner may override any answer below). Full text: [ADAPTER_ISOLATION.md](ADAPTER_ISOLATION.md). (HANDOFF previously called this "D-008"; D-008 is the persistence decision.)  
**Decision (summary):** Adapters run user agents only as separate processes (argv list, no shell, absolute allow-listed executable with recorded SHA-256, empty env + named allow-list, temp cwd, wall-clock timeout with process-group kill, byte caps on stdout/stderr, POSIX rlimits) or as allow-listed HTTP endpoints (SSRF guard, no redirects, size caps). Commands/URLs come only from a local user-authored config, never from case files or traces; adapters are off by default; failures become recorded failed results; missing protections fail closed. Tier A (these guard rails) does **not** restrict filesystem/network access of the child; Tier B (bubblewrap/nsjail/container) does but needs an external tool.  
**Reason:** D-004 (traces are data) and D-007 (runner failures are results). The design is honest about what a plain subprocess cannot prevent.  
**Answers (see ADAPTER_ISOLATION.md section 10):** (1) Tier A ships first, labelled trusted-code-only, and a config entry must carry an explicit trust acknowledgement; (2) Tier B targets bubblewrap (optional external tool, never a Python dependency; Docker/podman only later, same fail-closed rule); (3) Linux implemented and tested first, macOS only after it is tested there, Windows refuses; (4) defaults 30 s / 1 MB / 512 MB kept, overridable per adapter up to the hard maxima.  
**Note:** acceptance does not mean implemented: nothing in D-010 is built or tested yet.

## D-011: License = MIT
**Status:** ACCEPTED 2026-10-18 (owner delegated the choice).  
**Decision:** MIT, "Copyright (c) 2026 AgentProof contributors".  
**Reason:** maximum adoption, shortest text, exactly reproducible. Apache-2.0 (explicit patent grant) was the alternative; its official text could not be fetched in the session (apache.org blocked by the egress proxy) and is not reproduced from memory. Switching before the first release or outside contributions is cheap; after contributions it needs contributor consent.
