#!/usr/bin/env bash
# Narrated demo against the running services. Start ./run.sh first in another terminal.
# Pass --no-pause to run straight through.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run ./setup.sh first."; exit 1; }
exec .venv/bin/python scripts/demo.py "$@"
