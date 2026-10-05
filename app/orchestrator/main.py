"""Orchestrator: the integration layer between Solaria's CRM and CALL-E.

  POST /campaigns/payment-reminders   read accounts from CRM -> guards -> create CALL-E calls
  POST /calle/webhook                 CALL-E terminal event -> verify via API -> rules -> CRM write
  POST /calls/{call_id}/sync          polling fallback when no webhook arrives (e.g. no public URL)
  POST /outbox/retry                  re-send CRM writes that failed earlier
  GET  /calls, /outbox, /notifications, /         inspection for the demo
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import agent_config
from .calle_gateway import CalleGateway, GatewayError, build_gateway
from .crm_client import CrmClient, CrmError
from .guards import check_account
from .outcomes import decide
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {"completed", "failed", "canceled"}
EVENT_TYPES = {"call.completed", "call.failed", "call.result_validation_failed"}


class CampaignIn(BaseModel):
    account_ids: list[str] | None = None
    cycle: str = "2026-10"
    now: str | None = None  # ISO timestamp override for demos/tests; default = real clock


def create_app(gateway: CalleGateway | None = None, crm: CrmClient | None = None, db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="Solaria Payment Reminder Orchestrator", version="2.0")
    gw = gateway or build_gateway()
    crm_client = crm or CrmClient.from_url(os.environ.get("CRM_BASE_URL", "http://127.0.0.1:8001"))
    store = Store(db_path or os.environ.get("ORCH_DB", str(ROOT / "data" / "orchestrator.sqlite3")))
    webhook_url = os.environ.get("PUBLIC_WEBHOOK_URL") if gw.mode == "live" else os.environ.get(
        "SIM_WEBHOOK_URL", "http://127.0.0.1:8000/calle/webhook")
    app.state.store, app.state.gateway, app.state.crm = store, gw, crm_client

    # ------------------------------------------------------------------ outbound
    @app.post("/campaigns/payment-reminders")
    def run_campaign(body: CampaignIn) -> dict[str, Any]:
        now_utc = datetime.fromisoformat(body.now) if body.now else datetime.now(timezone.utc)
        call_date = now_utc.astimezone(ZoneInfo("America/Mexico_City")).date().isoformat()
        try:
            accounts = (
                [crm_client.get_account(a) for a in body.account_ids] if body.account_ids else crm_client.list_accounts()
            )
        except CrmError as exc:
            # Could not read customer context: place no calls at all.
            raise HTTPException(502, f"Campaign aborted, CRM read failed: {exc}") from exc

        results = []
        for acc in accounts:
            key = agent_config.idempotency_key(acc["account_id"], body.cycle)
            existing = store.get_request(key)
            if existing and existing["call_id"]:
                results.append({"account_id": acc["account_id"], "result": "skipped_already_called", "call_id": existing["call_id"]})
                continue
            guard = check_account(acc, now_utc)
            if not guard.allowed:
                store.save_intent(key, acc, body.cycle, call_date, None, f"blocked:{guard.code}", guard.detail)
                if guard.code in {"missing_phone", "invalid_phone"}:
                    _write_crm(store, crm_client, acc["account_id"], f"local-{key}", {
                        "call_id": f"local-{key}", "source": "orchestrator", "outcome": "not_called",
                        "new_status": "contact_data_missing", "review_reasons": [guard.code],
                        "task": {"type": "fix_contact_data", "team": "data_quality", "priority": "normal",
                                 "due_date": None, "description": f"Reminder call blocked: {guard.detail}"}})
                results.append({"account_id": acc["account_id"], "result": "blocked", "reason": guard.code, "detail": guard.detail})
                continue

            request = agent_config.build_request(acc, call_date=call_date, cycle=body.cycle, webhook_url=webhook_url)
            # Save intent + idempotency key BEFORE the network call, so a crash cannot cause a double call.
            store.save_intent(key, acc, body.cycle, call_date, request, "submitting")
            try:
                created = gw.create_call(request, key)
            except GatewayError as exc:
                store.update_request(key, state="submit_failed", detail=str(exc))
                results.append({"account_id": acc["account_id"], "result": "submit_failed", "detail": str(exc)})
                continue
            store.update_request(key, call_id=created["id"], state="submitted")
            results.append({"account_id": acc["account_id"], "result": "submitted", "call_id": created["id"],
                            "phone": agent_config.mask_phone(acc["phone_e164"])})
        return {"mode": gw.mode, "call_date": call_date, "results": results}

    # ------------------------------------------------------------------ inbound
    @app.post("/calle/webhook")
    async def calle_webhook(request: Request) -> JSONResponse:
        raw = await request.body()
        header_event_id = request.headers.get("CALL-E-Event-Id")
        try:
            event = json.loads(raw)
            event_id, event_type, call_id = event["id"], event["type"], event["data"]["id"]
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "malformed event"}, status_code=400)
        # Webhooks are unsigned: header/body id equality is a consistency check, NOT authentication.
        if header_event_id != event_id or event_type not in EVENT_TYPES:
            return JSONResponse({"error": "event id/type check failed"}, status_code=400)
        if store.get_by_call_id(call_id) is None:
            return JSONResponse({"result": "ignored", "reason": "unknown call id"}, status_code=202)
        if store.get_event(event_id) is None:
            store.save_event(event_id, call_id, event_type, raw.decode())
        result = process_call(call_id, trigger=f"webhook:{event_type}")
        return JSONResponse(result, status_code=result.pop("_http", 200))

    @app.post("/calls/{call_id}/sync")
    def sync_call(call_id: str) -> JSONResponse:
        if store.get_by_call_id(call_id) is None:
            raise HTTPException(404, "unknown call id")
        result = process_call(call_id, trigger="poll")
        return JSONResponse(result, status_code=result.pop("_http", 200))

    def process_call(call_id: str, trigger: str) -> dict[str, Any]:
        req = store.get_by_call_id(call_id)
        if req["state"] == "synced":
            return {"result": "duplicate", "call_id": call_id, "crm_sync": "synced"}
        # Trust boundary: the webhook body is only a wake-up signal. Re-read the call from CALL-E.
        try:
            snapshot = gw.get_call(call_id)
        except GatewayError as exc:
            store.update_request(req["idempotency_key"], detail=f"verify failed: {exc}")
            return {"result": "verify_failed", "call_id": call_id, "detail": str(exc), "_http": 503}
        if snapshot.get("status") not in TERMINAL:
            return {"result": "not_terminal", "call_id": call_id, "status": snapshot.get("status"), "_http": 202}

        account = json.loads(req["account_json"])
        decision = decide(snapshot, account, req["call_date"])
        payload = {
            "call_id": call_id,
            "source": "calle_simulated" if snapshot.get("simulated") else "calle_live",
            "outcome": decision.outcome,
            "new_status": decision.new_status,
            "review_reasons": decision.review_reasons,
            "task": decision.task,
            **decision.fields,
        }
        store.update_request(req["idempotency_key"], outcome=decision.outcome, crm_status=decision.new_status)
        crm = _write_crm(store, crm_client, account["account_id"], call_id, payload)
        if crm["crm_sync"] != "synced":
            print(f"WARNING: CRM write failed for {call_id}: {crm['error']}")
        store.update_request(req["idempotency_key"], state="synced", detail=trigger)
        if decision.send_payment_link:
            store.add_notification(account["account_id"], call_id, "sms",
                                   f"Solaria: enlace de pago para su referencia {account['payment_reference']}")
        return {"result": "processed", "call_id": call_id, "outcome": decision.outcome,
                "crm_status": decision.new_status, "review_reasons": decision.review_reasons,
                "crm_sync": "synced", "crm_confirmation": crm.get("confirmation")}

    @app.post("/outbox/retry")
    def retry_outbox() -> dict[str, Any]:
        out = []
        for item in store.outbox_pending():
            crm = _write_crm(store, crm_client, item["account_id"], item["call_id"], item["payload"])
            req = store.get_by_call_id(item["call_id"])
            if crm["crm_sync"] == "synced":
                if req:
                    store.update_request(req["idempotency_key"], state="synced", detail="outbox retry")
            out.append({"call_id": item["call_id"], **crm})
        return {"retried": out}

    # ------------------------------------------------------------------ inspection
    @app.get("/calls")
    def calls() -> list[dict[str, Any]]:
        return store.list_requests()

    @app.get("/calls/{call_id}/snapshot")
    def snapshot(call_id: str) -> dict[str, Any]:
        try:
            return gw.get_call(call_id)
        except GatewayError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/outbox")
    def outbox() -> list[dict[str, Any]]:
        return store.outbox_all()

    @app.get("/notifications")
    def notifications() -> list[dict[str, Any]]:
        return store.notifications()

    @app.get("/agent-config")
    def agent_cfg() -> dict[str, Any]:
        return {"schema_version": agent_config.SCHEMA_VERSION, "result_schema": agent_config.RESULT_SCHEMA}

    @app.get("/", response_class=HTMLResponse)
    def view() -> str:
        rows = "".join(
            f"<tr><td>{r['account_id']}</td><td>{r['call_id'] or ''}</td><td><b>{r['state']}</b></td>"
            f"<td>{r['outcome'] or ''}</td><td>{r['crm_status'] or ''}</td><td>{(r['detail'] or '')[:90]}</td></tr>"
            for r in store.list_requests()
        )
        ob = "".join(f"<tr><td>{o['call_id']}</td><td>{o['state']}</td><td>{o['attempts']}</td><td>{o['last_error'] or ''}</td></tr>"
                     for o in store.outbox_all())
        return (
            "<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='3'><title>Orchestrator</title>"
            "<style>body{font-family:system-ui;margin:24px}table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ddd;padding:6px;font-size:14px;text-align:left}th{background:#eee}</style></head><body>"
            f"<h1>Payment Reminder Orchestrator</h1><p>CALL-E mode: <b>{gw.mode.upper()}</b></p>"
            "<h2>Calls</h2><table><tr><th>Account</th><th>Call id</th><th>State</th><th>Outcome</th><th>CRM status</th><th>Detail</th></tr>"
            f"{rows}</table><h2>CRM outbox</h2><table><tr><th>Call</th><th>State</th><th>Attempts</th><th>Last error</th></tr>{ob}</table>"
            "</body></html>"
        )

    return app


def _write_crm(store: Store, crm: CrmClient, account_id: str, call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Write through an outbox: record the intent first, then mark synced only on CRM confirmation."""
    store.outbox_put(call_id, account_id, payload)
    try:
        confirmation = crm.write_outcome(account_id, payload)
    except CrmError as exc:
        store.outbox_mark(call_id, "pending" if exc.retryable else "dead_letter", str(exc))
        return {"crm_sync": "failed", "retryable": exc.retryable, "error": str(exc)}
    store.outbox_mark(call_id, "synced")
    return {"crm_sync": "synced", "confirmation": confirmation}

