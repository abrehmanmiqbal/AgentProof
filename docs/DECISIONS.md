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
**Status:** Pending implementation  
**Decision:** Inspect available repository files and tooling before choosing the full dependency stack.  
**Reason:** Avoid unnecessary complexity and unsupported assumptions.
