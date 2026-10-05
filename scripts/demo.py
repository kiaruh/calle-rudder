"""Narrated live demo against the running services (./run.sh in another terminal).

    python3 scripts/demo.py            # pauses between acts (for presenting)
    python3 scripts/demo.py --no-pause # straight through (for recording evidence)

Uses CALL-E SIMULATED mode unless the orchestrator was started with CALLE_MODE=live.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import httpx

ORCH = "http://127.0.0.1:8000"
CRM = "http://127.0.0.1:8001"
PAUSE = "--no-pause" not in sys.argv
# Demo clock: noon in Mexico City, inside the calling window, whatever time you present.
NOW = "2026-10-05T18:00:00+00:00"


def act(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)
    if PAUSE:
        input("  [Enter] ")


def show(obj, keys=None) -> None:
    if keys and isinstance(obj, list):
        obj = [{k: o.get(k) for k in keys} for o in obj]
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def wait_for(predicate, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.5)
    return False


def main() -> None:
    h = httpx.Client(timeout=15)
    try:
        h.post(f"{CRM}/admin/reset")
        h.get(f"{ORCH}/calls").raise_for_status()
    except httpx.HTTPError:
        sys.exit("Can't reach the services on :8000/:8001. Start them with ./run.sh, or use ./demo.sh, which starts them for you.")

    act("ACT 1 - Input: customer context in the CRM (fictional data)")
    show(h.get(f"{CRM}/accounts/ACC-1001").json())

    act("ACT 2 - Run the payment-reminder campaign (guards run before any call)")
    res = h.post(f"{ORCH}/campaigns/payment-reminders", json={"now": NOW}).json()
    show(res)

    act("ACT 3 - CALL-E finishes calls and POSTs webhooks; orchestrator verifies + writes CRM")
    submitted = [r for r in res["results"] if r["result"] == "submitted"]
    wait_for(lambda: all(c["state"] in {"synced", "crm_sync_failed"} for c in h.get(f"{ORCH}/calls").json()
                         if c["call_id"] and not c["call_id"].startswith("local-")))
    show(h.get(f"{ORCH}/calls").json(), ["account_id", "state", "outcome", "crm_status", "detail"])
    print("\nCRM follow-up tasks (output another team acts on):")
    show(h.get(f"{CRM}/tasks").json(), ["account_id", "type", "team", "priority", "due_date", "description"])

    act("ACT 4 - Field mapping for one call: CALL-E structured_result -> CRM interaction")
    ptp = next(c for c in h.get(f"{ORCH}/calls").json() if c["account_id"] == "ACC-1001")
    snap = h.get(f"{ORCH}/calls/{ptp['call_id']}/snapshot").json()
    print("CALL-E structured_result:")
    show(snap["structured_result"])
    print("CRM interaction record:")
    show(next(i for i in h.get(f"{CRM}/interactions").json() if i["call_id"] == ptp["call_id"]))

    act("ACT 5 - Integration failure: CRM goes down while a call is in progress")
    r = h.post(f"{ORCH}/campaigns/payment-reminders",
               json={"account_ids": ["ACC-1001"], "cycle": "2026-11", "now": NOW}).json()
    show(r)
    show(h.post(f"{CRM}/admin/failure", json={"mode": "error"}).json())
    print("...waiting for CALL-E webhook...")
    wait_for(lambda: any(c["cycle"] == "2026-11" and c["state"] == "crm_sync_failed"
                         for c in h.get(f"{ORCH}/calls").json() if "cycle" in c) or
             any(o["state"] == "pending" for o in h.get(f"{ORCH}/outbox").json()))
    show([c for c in h.get(f"{ORCH}/calls").json() if c["idempotency_key"].startswith("solaria-reminder-2026-11")],
         ["account_id", "state", "outcome", "detail"])
    print("Outbox:")
    show([o for o in h.get(f"{ORCH}/outbox").json() if o["state"] != "synced"])

    act("ACT 6 - CRM recovers; outbox retry delivers exactly once")
    show(h.post(f"{CRM}/admin/failure", json={"mode": "none"}).json())
    show(h.post(f"{ORCH}/outbox/retry").json())
    show([c for c in h.get(f"{ORCH}/calls").json() if c["idempotency_key"].startswith("solaria-reminder-2026-11")],
         ["account_id", "state", "outcome", "crm_status"])

    print(f"\nDone {datetime.now(timezone.utc).isoformat(timespec='seconds')}. Dashboards: {ORCH}/  {CRM}/")


if __name__ == "__main__":
    main()
