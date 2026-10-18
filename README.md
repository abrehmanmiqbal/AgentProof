# AgentProof

**Open-source reliability engineering for AI agents.** Capture a behavior, turn it into a regression case, rerun it, and get an explicit assertion-based result.

AgentProof is being built free-first: the core demo should run locally without paid APIs, cloud hosting, or provider credentials.

## Project status

Early development. The deterministic core, SQLite persistence, comparison engine, and CLI are implemented and tested locally (see docs/TEST_EVIDENCE.md). HTTP API, UI, report export, real-agent adapters, and release readiness are not yet implemented.

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

## Try the full loop offline

```bash
cat > case.json <<'JSON'
{"case_id":"greet-ava","name":"Greet Ava","input":{"action":"greet","name":"Ava"},
 "assertions":[{"path":"message","operator":"equals","expected":"Hello, Ava!"}]}
JSON
agentproof case add case.json
agentproof run greet-ava --label before --runner local-legacy   # fails (exit 1)
agentproof run greet-ava --label after  --runner local          # passes
agentproof compare 1 2                                          # verdict: improved
agentproof report 1 2                                           # deterministic Markdown report (--format json also)
```

Data is stored in `./agentproof.db` (override with `--db` or `AGENTPROOF_DB`). `compare` and `report` exit 1 if the verdict is `regressed`.

## First vertical slice

- Typed regression-case and result models.
- A deterministic local runner for offline demos.
- Explicit assertions against structured outputs.
- A regression engine that returns reproducible pass/fail details.

## Planned

See [docs/TASKS.md](docs/TASKS.md) for milestones and [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) for verified progress.

## Security principles

Recorded inputs and traces are data, not code. AgentProof must not execute arbitrary imported traces. Never commit secrets or real personal/medical data.
