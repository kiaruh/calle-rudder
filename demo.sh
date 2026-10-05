#!/usr/bin/env bash
# Narrated demo. Uses the services from ./run.sh if they are already running;
# otherwise starts them for the duration of the demo.
# Pass --no-pause to run straight through.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "Run ./setup.sh first."; exit 1; fi
PY=.venv/bin/python

services_up() {
  $PY - <<'PYEOF' 2>/dev/null
import httpx, sys
try:
    httpx.get("http://127.0.0.1:8000/calls", timeout=1).raise_for_status()
    httpx.get("http://127.0.0.1:8001/accounts", timeout=1).raise_for_status()
except Exception:
    sys.exit(1)
PYEOF
}

STARTED_PID=""
if ! services_up; then
  mkdir -p logs
  echo "Services not running. Starting them (output in logs/services.log) ..."
  OPEN_BROWSER=0 ./run.sh > logs/services.log 2>&1 &
  STARTED_PID=$!
  trap 'kill $STARTED_PID 2>/dev/null || true' EXIT
  for _ in $(seq 1 40); do
    if services_up; then break; fi
    if ! kill -0 "$STARTED_PID" 2>/dev/null; then
      echo "The services failed to start. Last lines of logs/services.log:"; tail -20 logs/services.log; exit 1
    fi
    sleep 0.5
  done
  if ! services_up; then echo "Services did not come up in 20s. See logs/services.log"; exit 1; fi
  echo "Services are up."
fi

$PY scripts/demo.py "$@"

if [ -n "$STARTED_PID" ] && [[ " $* " != *" --no-pause "* ]]; then
  echo
  read -r -p "Dashboards: http://127.0.0.1:8000/ and http://127.0.0.1:8001/  - press Enter to stop the services. " _ || true
fi
