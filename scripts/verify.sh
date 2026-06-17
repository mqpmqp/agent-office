#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON=python
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
  elif command -v python.exe >/dev/null 2>&1; then
    PYTHON=python.exe
  else
    echo "python not found" >&2
    exit 127
  fi
fi

TASK_ID="VERIFY-DEMO"

"$PYTHON" -m compileall -q agent_office
"$PYTHON" -m agent_office --help >/dev/null
"$PYTHON" -m agent_office run-demo "$TASK_ID" --mock --reset
"$PYTHON" -m agent_office status "$TASK_ID"

echo "verify ok"
