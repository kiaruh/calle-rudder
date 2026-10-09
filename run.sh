#!/usr/bin/env bash
# Start the mock CRM (:8001) and the orchestrator (:8000). Ctrl+C stops both.
# Usage: ./run.sh            (fresh databases)
#        KEEP_DATA=1 ./run.sh (keep previous state)
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
if [ ! -x .venv/bin/python ]; then echo "Run ./setup.sh first (creates .venv and installs dependencies)."; exit 1; fi
PY=.venv/bin/python
if [ "${KEEP_DATA:-0}" != "1" ]; then rm -f data/crm.sqlite3 data/orchestrator.sqlite3; fi
mkdir -p logs

# Stop both servers on Ctrl+C, on kill, or if either one exits.
cleanup() { trap - EXIT INT TERM; kill $(jobs -p) 2>/dev/null || true; }
trap cleanup EXIT INT TERM

$PY -m uvicorn app.crm.main:create_app --factory --host 127.0.0.1 --port 8001 --log-level warning > logs/crm.log 2>&1 &
$PY -m uvicorn app.orchestrator.main:create_app --factory --host 127.0.0.1 --port 8000 --log-level info &
echo
echo "  Control center  ->  http://127.0.0.1:8000/        (start here: demo buttons, call my phone, troubleshoot)"
echo "  Project guide   ->  http://127.0.0.1:8000/learn   (diagrams + docs)"
echo "  Learn AI Rudder ->  http://127.0.0.1:8000/rudder/ (interview study guide + video; also a tab in the control center)"
echo "  Mock CRM        ->  http://127.0.0.1:8001/"
echo "  API docs        ->  http://127.0.0.1:8000/docs  and  http://127.0.0.1:8001/docs"
echo "  CALL-E mode     ->  ${CALLE_MODE:-simulated} (switch to live from the 'Call my phone' tab)"
echo
echo "Press Ctrl+C to stop."
# Open the control center in the browser (macOS 'open' / Linux 'xdg-open'). Disable with OPEN_BROWSER=0.
if [ "${OPEN_BROWSER:-1}" = "1" ]; then
  (sleep 2; if command -v open >/dev/null; then open http://127.0.0.1:8000/; elif command -v xdg-open >/dev/null; then xdg-open http://127.0.0.1:8000/ >/dev/null 2>&1; fi) &
fi
wait
