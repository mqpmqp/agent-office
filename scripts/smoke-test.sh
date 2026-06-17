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

TASK_ID="${1:-demo-task}"
"$PYTHON" -m agent_office run-demo "$TASK_ID" --mock --reset

echo "smoke test ok: $TASK_ID"
