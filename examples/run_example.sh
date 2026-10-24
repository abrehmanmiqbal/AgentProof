#!/usr/bin/env bash
# Offline end-to-end walk-through: failure -> fix -> rerun -> compare -> report.
# Uses a throwaway database in a temp dir; nothing is written to your working directory.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export REGRESSAGENT_DB="$tmp/demo.db"

for f in "$here"/cases/*.json; do regressagent case add "$f" || exit 2; done

echo "== before: the legacy runner has a greeting bug (exit 1 expected)"
regressagent run greet-ava --label before --runner local-legacy
echo "exit=$?"

echo "== after: the fixed runner (exit 0 expected)"
regressagent run greet-ava --label after --runner local
echo "exit=$?"

echo "== compare run 1 (before) with run 2 (after)"
regressagent compare 1 2
echo "== report"
regressagent report 1 2
