# AgentProof

**Open-source reliability engineering for AI agents.** Capture a behavior, turn it into a regression case, rerun it, and get an explicit assertion-based result.

AgentProof is being built free-first: the core demo should run locally without paid APIs, cloud hosting, or provider credentials.

## Project status

Early development. The initial deterministic core is being implemented. APIs, persistence, UI, external model integrations, and release readiness are not yet claimed as complete.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

## First vertical slice

- Typed regression-case and result models.
- A deterministic local runner for offline demos.
- Explicit assertions against structured outputs.
- A regression engine that returns reproducible pass/fail details.

## Planned

See [docs/TASKS.md](docs/TASKS.md) for milestones and [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) for verified progress.

## Security principles

Recorded inputs and traces are data, not code. AgentProof must not execute arbitrary imported traces. Never commit secrets or real personal/medical data.
