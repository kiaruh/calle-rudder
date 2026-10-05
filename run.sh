#!/usr/bin/env bash
# Start the mock CRM (:8001) and the orchestrator (:8000). Ctrl+C stops both.
# Usage: ./run.sh            (fresh databases)
#        KEEP_DATA=1 ./run.sh (keep previous state)
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
if [ "${KEEP_DATA:-0}" != "1" ]; then rm -f data/crm.sqlite3 data/orchestrator.sqlite3; fi
mkdir -p logs
python3 -m uvicorn app.crm.main:create_app --factory --port 8001 --log-level warning > logs/crm.log 2>&1 &
CRM_PID=$!
trap 'kill $CRM_PID 2>/dev/null' EXIT
echo "Mock CRM      -> http://127.0.0.1:8001   (SIMULATED system)"
echo "Orchestrator  -> http://127.0.0.1:8000   (CALL-E mode: ${CALLE_MODE:-simulated})"
echo "API docs      -> http://127.0.0.1:8000/docs  and  http://127.0.0.1:8001/docs"
python3 -m uvicorn app.orchestrator.main:create_app --factory --port 8000 --log-level info
