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
