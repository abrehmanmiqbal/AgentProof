"""Deterministic, timestamp-free reports rendered from a :class:`Comparison`.

Everything in a comparison can originate from untrusted case/trace data, so every
interpolated value is whitespace-collapsed, length-limited and has Markdown/HTML-significant
characters neutralised as entities before it reaches the output.
"""
from __future__ import annotations

import json

from .comparison import AssertionChange, Comparison

MAX_CELL_CHARS = 80
MAX_ERROR_CHARS = 300
_EMPTY = "—"
_ENTITIES = {
    "|": "&#124;",
    "`": "&#96;",
    "<": "&lt;",
    ">": "&gt;",
    "[": "&#91;",
    "]": "&#93;",
}


def _clean(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return "".join(_ENTITIES.get(ch, ch) for ch in text)


def _value(value: object) -> str:
    return _clean(json.dumps(value, ensure_ascii=False, default=str), MAX_CELL_CHARS)


def _label(change: AssertionChange) -> str:
    return change.value.replace("_", " ")


def _yes_no(flag: bool | None) -> str:
    return "unknown" if flag is None else ("yes" if flag else "no")


def render_markdown(comparison: Comparison) -> str:
    c = comparison
    before_id = "n/a" if c.before_run_id is None else str(c.before_run_id)
    after_id = "n/a" if c.after_run_id is None else str(c.after_run_id)
    lines = [
        f"# AgentProof report: {_clean(c.case_id, MAX_CELL_CHARS)}",
        "",
        f"- Verdict: **{c.verdict.value.upper()}**",
        f"- Before run: {before_id}",
        f"- After run: {after_id}",
        f"- Same case definition: {_yes_no(c.same_case_definition)}",
        "",
    ]

    counts = [
        f"{n} {_label(ch)}"
        for ch in AssertionChange
        if (n := sum(1 for d in c.diffs if d.change == ch))
    ]
    lines += [f"Summary: {', '.join(counts) if counts else 'no assertions'}", ""]

    if c.before_error or c.after_error:
        lines += ["## Run errors", ""]
        if c.before_error:
            lines.append(f"- Before: {_clean(c.before_error, MAX_ERROR_CHARS)}")
        if c.after_error:
            lines.append(f"- After: {_clean(c.after_error, MAX_ERROR_CHARS)}")
        lines.append("")

    lines += ["## Assertion changes", ""]
    if c.diffs:
        lines += [
            "| Path | Operator | Change | Before | After |",
            "| --- | --- | --- | --- | --- |",
        ]
        for d in c.diffs:
            before = _EMPTY if d.change == AssertionChange.ADDED else _value(d.before_actual)
            after = _EMPTY if d.change == AssertionChange.REMOVED else _value(d.after_actual)
            lines.append(
                f"| {_clean(d.path, MAX_CELL_CHARS)} | {d.operator.value} "
                f"| {_label(d.change)} | {before} | {after} |"
            )
    else:
        lines.append("No assertion differences recorded.")
    return "\n".join(lines) + "\n"


def render_json(comparison: Comparison) -> str:
    return json.dumps(comparison.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
