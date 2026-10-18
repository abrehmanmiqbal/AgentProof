# AgentProof

**Open-source reliability engineering for AI agents.** Capture a behavior, turn it into a regression case, rerun it, and get an explicit assertion-based result.

AgentProof is built free-first: the core loop runs locally without paid APIs, cloud hosting, or provider credentials.

## Project status

Early development. Implemented and tested locally and in CI (Python 3.11 and 3.12): typed models, deterministic offline runners, assertion engine, SQLite persistence, before/after comparison, Markdown/JSON reports, and the CLI below. **Not implemented yet:** HTTP API, UI, trace import, adapters for real agents (and therefore no way yet to test an actual agent; only the built-in demo runners exist), HTML reports. See [docs/TASKS.md](docs/TASKS.md) and [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

## Install

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
pytest && agentproof demo
```

## The loop in 60 seconds

```bash
./examples/run_example.sh        # uses a throwaway database; prints every step
```

Or by hand:

```bash
agentproof case add examples/cases/greet.json
agentproof run greet-ava --label before --runner local-legacy   # fails, exit 1
agentproof run greet-ava --label after  --runner local          # passes, exit 0
agentproof compare 1 2                                          # verdict: improved
agentproof report 1 2 --output report.md                        # shareable report
```

## Case files

A case is one JSON file: an input for the agent plus the assertions its structured output must satisfy.

```json
{
  "case_id": "greet-ava",
  "name": "Agent greets a user by name",
  "input": {"action": "greet", "name": "Ava"},
  "assertions": [
    {"path": "message", "operator": "equals", "expected": "Hello, Ava!"},
    {"path": "message", "operator": "regex", "expected": "^Hello, \\w+!$"}
  ]
}
```

Limits (all enforced when the file is loaded; unknown fields are rejected): file <= 1,000,000 bytes; `case_id` 1-128 chars; `name` 1-256 chars; 1-100 assertions. Case files are parsed as JSON only and are never executed. More samples are in [`examples/cases/`](examples/cases/).

### Paths

`path` is dot-separated: `echo.tag`, or `items.0.name` for list index 0 (ASCII digits only). A key that itself contains `.` cannot be addressed yet.

### Operators

| Operator | `expected` | Passes when |
|---|---|---|
| `exists` | ignored | the path exists |
| `equals` | any JSON value | actual equals expected; `true` never equals `1`; `1` equals `1.0` |
| `not_equals` | any JSON value | the opposite of `equals` (a missing path fails) |
| `contains` | any JSON value | Python `in`: substring for strings, membership for lists, key for objects |
| `gt` / `lt` | finite number | actual is a number (not a boolean) strictly greater / less than expected |
| `regex` | pattern string | actual is a string and `re.search(pattern, actual)` finds a match |

Every operator except `exists` fails if the path is missing. Use `^...$` to anchor a regex.

**Regex limits (ReDoS protection, [D-009](docs/DECISIONS.md)).** Python's regex engine cannot be interrupted, so unsafe patterns are rejected up front when the case is loaded: at most 200 characters; no backreferences or conditionals; at most one unbounded repeat (`*`, `+`, `{n,}`); no repeat nested in another repeat; no `|` alternation inside a repeat; repeat counts <= 100. Matched text longer than 5,000 characters makes the assertion fail (it is never truncated). Some harmless patterns are rejected too, e.g. `\w+@\w+\.\w+` or `(foo|bar)+`. This is a mitigation, not a proof of safety.

## CLI reference

```
agentproof [--db FILE] <command> ...
```

`--db FILE` (or the `AGENTPROOF_DB` environment variable) selects the SQLite file; default `./agentproof.db`. It goes **before** the command. All commands print JSON unless noted; errors go to stderr as `error: ...`.

| Command | What it does |
|---|---|
| `demo` | Runs a built-in case offline; no database needed. Exit 0 if it passes. |
| `case add FILE [--overwrite]` | Validates and saves a case. Prints `{"saved": true, "case_hash": ...}`. Fails (exit 2) if the id exists unless `--overwrite`. |
| `case list` | JSON list of case ids. |
| `case show CASE_ID` | Prints the saved case. |
| `case delete CASE_ID --yes` | Deletes the case **and all its runs**. Refuses (exit 2) without `--yes`. |
| `run CASE_ID --label L [--runner R] [--repeat N]` | Runs the case and records it. Prints `run_id`, `passed`, `error`. With `--repeat N` (1-20) it records N runs and prints `run_ids`, `total`, `passed`, `failed`, and `stable` (true when every repeat had identical per-assertion outcomes). Exit 1 if any run failed. |
| `run-all --label L [--runner R] [--repeat N]` | Runs and records every saved case. Exit 1 if any fail; exit 2 if there are no cases. With `--repeat N` (1-20) each case runs N times; each result gets `run_ids`, `total`, `passed`, `failed`, `stable`, and the top level adds `unstable` (case ids whose repeats differed). Top-level `passed`/`failed` count cases (a case passes only if every repeat passed). |
| `runs CASE_ID` | Lists recorded runs (id, label, runner, passed, timestamp). |
| `compare BEFORE_ID AFTER_ID` | Assertion-level diff of two runs with a verdict: `improved`, `regressed`, or `unchanged`. Exit 1 if `regressed`. |
| `report BEFORE_ID AFTER_ID [--format markdown\|json] [--output FILE] [--force]` | Deterministic, timestamp-free report (Markdown by default) on stdout. `--output` writes a file instead and refuses to overwrite one without `--force`. Exit 1 if `regressed`. |

Runners (`--runner`): `local` (default; deterministic offline demo agent) and `local-legacy` (same, but with a deliberate greeting bug so you can see a failure turn into a fix). They are demo runners, not real agents.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success / all assertions passed / verdict not `regressed` |
| 1 | a run failed, or the verdict was `regressed` |
| 2 | usage or input error (invalid case file, unknown case/run, refused overwrite or delete, corrupt database) |

A runner result larger than 1,000,000 bytes is not lost: it is recorded as a failed run with an explanatory `error`. Recorded runs are immutable and store the SHA-256 of the exact case definition, so `compare` can tell you whether both runs used the same case.

## Security principles

Recorded inputs, traces, and case files are data, not code. AgentProof must not execute arbitrary imported traces, and any adapter that runs user code or commands needs a documented isolation design first ([docs/DECISIONS.md](docs/DECISIONS.md)). Never commit secrets or real personal/medical data. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for what is and is not mitigated (notably: stored outputs are not redacted). AgentProof is released under the [MIT License](LICENSE) (D-011); see [CONTRIBUTING.md](CONTRIBUTING.md).

## Development

`ruff check . && pytest`. Project memory lives in [AGENTS.md](AGENTS.md) and [docs/](docs/); [docs/TEST_EVIDENCE.md](docs/TEST_EVIDENCE.md) lists exactly what has been run and what has not.
