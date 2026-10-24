"""Fuzz the regex validator: generate random patterns, then time every ACCEPTED pattern
against adversarial texts in a subprocess (hard timeout). Reports the slowest accepted one.

Usage: python scripts/fuzz_regex_safety.py [SEED] [COUNT]
Not part of the test suite (slow, timing-dependent). Evidence is recorded in TEST_EVIDENCE.md.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys

from regressagent.regex_safety import MAX_TEXT_LENGTH, UnsafeRegexError, validate_pattern

TOKENS = [
    "a", "b", "a*", "a+", "a?", "a{1,3}", "a{0,10}", "a{2}", "[ab]*", "[ab]+", ".", ".*", ".+",
    "\\w+", "\\s*", "(a+)", "(a|b)", "(?:ab)*", "(?:ab){1,5}", "(a*)", "(a|ab)", "x", "$", "^",
    "(?:a|a)+", "(.*a)", "(?:a?){1,20}",
]  # fmt: skip
TIMER = (
    "import re,sys,time,json\n"
    "p=sys.argv[1];m=0\n"
    "for t in json.loads(sys.argv[2]):\n"
    "    s=time.perf_counter();re.search(p,t);m=max(m,time.perf_counter()-s)\n"
    "print(m)"
)


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1234
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
    rng = random.Random(seed)
    n = MAX_TEXT_LENGTH
    texts = [
        "a" * n, "ab" * (n // 2), "a" * (n - 1) + "c", "b" * n, " " * (n - 1) + "x",
        ("a" * 99 + "b") * (n // 100),
    ]  # fmt: skip
    accepted: set[str] = set()
    rejected = 0
    for _ in range(count):
        pat = "".join(rng.choice(TOKENS) for _ in range(rng.randint(1, 6)))
        if rng.random() < 0.3:
            pat = "(?:" + pat + ")" + rng.choice(["", "*", "+", "{1,5}", "{3}"])
        try:
            validate_pattern(pat)
            accepted.add(pat)
        except UnsafeRegexError:
            rejected += 1
    worst, worst_pat, timeouts = 0.0, None, []
    for pat in sorted(accepted):
        try:
            out = subprocess.run(
                [sys.executable, "-c", TIMER, pat, json.dumps(texts)],
                capture_output=True, text=True, timeout=30, check=True,
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            timeouts.append(pat)
            continue
        elapsed = float(out.stdout.strip())
        if elapsed > worst:
            worst, worst_pat = elapsed, pat
    print(f"seed={seed} generated={count} accepted_unique={len(accepted)} rejected={rejected}")
    print(f"slowest accepted single match: {worst:.2f}s {worst_pat!r}; >30s timeouts: {len(timeouts)}")
    return 1 if timeouts else 0


if __name__ == "__main__":
    raise SystemExit(main())
