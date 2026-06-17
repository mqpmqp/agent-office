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

TASK_ID="verify-task-$(date +%s)"

"$PYTHON" -m py_compile agent_office/*.py
"$PYTHON" -m agent_office --help >/dev/null
"$PYTHON" -m agent_office new "$TASK_ID"
"$PYTHON" -m agent_office context "$TASK_ID" --mock
"$PYTHON" -m agent_office implement "$TASK_ID" --mock
"$PYTHON" -m agent_office redteam "$TASK_ID" --mock
"$PYTHON" -m agent_office summarize "$TASK_ID" --mock
"$PYTHON" -m agent_office final "$TASK_ID" --mock
"$PYTHON" -m agent_office status "$TASK_ID"

echo "verify ok"
