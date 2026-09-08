#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

if [[ ! -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${PROJECT_DIR}/.venv"
fi

"${PROJECT_DIR}/.venv/bin/python" -m pip install -r "${PROJECT_DIR}/backend/requirements.txt"
npm --prefix "${PROJECT_DIR}/frontend" ci
npm --prefix "${PROJECT_DIR}/frontend" run build

echo
echo "Setup complete. Create the first administrator with:"
echo "  ${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/init_admin.py"
echo "Then start the application with:"
echo "  ${PROJECT_DIR}/start.sh"
