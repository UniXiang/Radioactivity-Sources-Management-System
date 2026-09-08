#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${PROJECT_DIR}/backend${PYTHONPATH:+:${PYTHONPATH}}"
PYTHON_BIN="${JCSMS_PYTHON:-${PROJECT_DIR}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi
exec "${PYTHON_BIN}" -m uvicorn app.main:app --host "${JCSMS_HOST:-0.0.0.0}" --port "${JCSMS_PORT:-8080}"
