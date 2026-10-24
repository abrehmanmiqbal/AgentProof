# Contributing to RegressAgent

Thanks for helping. Read `AGENTS.md` first: it holds the operating rules and security guardrails, and they apply to humans and AI agents alike.

## Setup
```
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && pytest && regressagent demo
```
All three must pass before and after your change (CI runs them on Python 3.11 and 3.12).

## Workflow
- Test-first: write the failing test, watch it fail, then implement. Optionally break the code on purpose to confirm the test can fail.
- Small, focused commits; one concern per pull request.
- Record what you actually ran in `docs/TEST_EVIDENCE.md` (exact commands, real numbers). Say what is NOT verified. Never claim a check you did not run.
- Update the project memory docs listed in `AGENTS.md` when behavior or decisions change.

## Security rules (non-negotiable)
- Case files, traces, runner output and any imported data are untrusted. Bound their size, parse them as data only, never evaluate them.
- No `eval`/`exec`/`subprocess`/network calls outside the accepted design in `docs/ADAPTER_ISOLATION.md` (D-010).
- Never commit secrets, tokens, `.env` files or personal data. Report vulnerabilities privately to the maintainer, not in a public issue.

## License
By contributing you agree your contribution is released under the MIT License (see `LICENSE`).
