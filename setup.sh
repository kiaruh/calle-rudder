#!/usr/bin/env bash
# One-time setup: creates a local virtual environment (.venv), installs dependencies, runs the tests.
# Works with Homebrew/macOS Python, where `pip` is missing and global installs are blocked (PEP 668).
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "python3 not found. Install it (e.g. 'brew install python') and retry."; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "Python 3.11+ required, found $("$PY" --version)."; exit 1; }
if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv with $("$PY" --version) ..."
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "Dependencies installed. Running tests ..."
.venv/bin/python -m pytest -q
echo
echo "Ready. Next: ./run.sh   (opens the control center at http://127.0.0.1:8000/)"
