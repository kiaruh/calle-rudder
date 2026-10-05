"""Control center API + pages (http://127.0.0.1:8000/).

Everything the UI buttons do is a plain JSON endpoint under /api, so each action can
also be run from the terminal with curl (the UI shows the exact command).

The API key typed into the UI is kept in memory only (lost on restart). To keep it,
put CALLE_API_KEY in .env instead.
"""

from __future__ import annotations

import json
import os
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from . import agent_config
from .calle_gateway import GatewayError, LiveCalleGateway, SimulatedCalleGateway
from .crm_client import CrmError
from .guards import CALLING_CODES, UNLISTED_CALLING_CODES, country_options, validate_phone
from .outcomes import extract_result

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / "static"
DEMO_NOW = "2026-10-05T18:00:00+00:00"  # 12:00 in Mexico City, inside the calling window

SCENARIOS = [
    {"id": "promise_firm", "test": "T1 normal", "title": "Firm promise to pay",
     "say": "Sí, soy yo. → El viernes nueve hago la transferencia por SPEI, los 2,450.",
     "expect": "CRM promise_to_pay + verify_payment task + SMS link"},
    {"id": "promise_ambiguous", "test": "T2 ambiguous", "title": "Vague answer",
     "say": "Sí, él habla. → Pues luego, cuando me paguen. → A fin de mes, si me pagan a tiempo.",
     "expect": "needs_review + confirm_promise task for a human, no SMS"},
    {"id": "human_requested", "test": "T4 exception", "title": "Asks for a human",
     "say": "Sí, ¿qué pasó? → Prefiero hablar con una persona. → Mañana después de las cinco.",
     "expect": "callback_requested + high-priority human_callback task"},
    {"id": "wrong_party", "test": "Exception", "title": "Wrong person answers",
     "say": "No, ella no está, soy su hermana. → En la noche, después de las ocho.",
     "expect": "wrong_party_contact, debt never mentioned"},
    {"id": "already_paid", "test": "Exception", "title": "Already paid",
     "say": "Sí, soy yo. → Ya pagué ayer en el OXXO, tengo mi ticket.",
     "expect": "paid_claimed + reconcile_payment task for finance"},
    {"id": "no_answer_failed", "test": "Exception", "title": "No answer",
     "say": "(Don't pick up.)",
     "expect": "call.failed → no_contact, no automatic redial"},
    {"id": "result_validation_failed", "test": "Exception", "title": "Result couldn't be extracted",
     "say": "(Simulated only.) Bad line, nothing usable said.",
     "expect": "needs_review + QA task"},
]


class FailureIn(BaseModel):
    mode: str


class ModeIn(BaseModel):
    mode: str


class KeyIn(BaseModel):
    api_key: str


class SimulateIn(BaseModel):
    scenario: str
    account_id: str = "ACC-1001"


class CampaignUIIn(BaseModel):
    account_ids: list[str] | None = None
    demo_clock: bool = True


class CallMeIn(BaseModel):
    phone: str
    region: str = "MX"
    locale: str = "es-MX"
    timezone: str = "America/Mexico_City"
    account_id: str = "ACC-1001"
    consent: bool = False


def register(app: FastAPI, rt, *, run_campaign: Callable, retry_outbox: Callable, sync_call: Callable) -> None:
    from .main import CampaignIn  # local import to avoid a cycle

    def ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:17]

    def ensure_sim() -> SimulatedCalleGateway:
        if rt.sim is None:
            rt.sim = SimulatedCalleGateway(
                webhook_url=os.environ.get("SIM_WEBHOOK_URL", "http://127.0.0.1:8000/calle/webhook"),
                delay_seconds=float(os.environ.get("SIM_DELAY_SECONDS", "3")))
        return rt.sim

    def crm_try(fn, default):
        try:
            return fn()
        except CrmError:
            return default

    # ------------------------------------------------------------------ pages
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/learn", include_in_schema=False)
    def learn() -> FileResponse:
        return FileResponse(STATIC / "learn.html")

    # ------------------------------------------------------------------ status
    @app.get("/api/status")
    def status() -> dict[str, Any]:
        crm_mode = crm_try(rt.crm.get_failure, "unreachable")
        return {
            "mode": rt.gw.mode,
            "api_key_set": bool(rt.api_key),
            "webhook": rt.webhook_url() or "polling (no PUBLIC_WEBHOOK_URL)",
            "crm": "unreachable" if crm_mode == "unreachable" else ("healthy" if crm_mode == "none" else f"outage:{crm_mode}"),
            "allowed_phones": [agent_config.mask_phone(p) for p in sorted(getattr(rt.live, "allowed", set()))],
            "regions": CALLING_CODES,
            "countries": country_options(),
        }

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        return {
            "status": status(),
            "calls": rt.store.list_requests(),
            "accounts": crm_try(rt.crm.list_accounts, None),
            "tasks": crm_try(rt.crm.list_tasks, None),
            "outbox": rt.store.outbox_all(),
            "notifications": rt.store.notifications(),
            "events": list(rt.events)[:60],
        }

    @app.get("/api/scenarios")
    def scenarios() -> list[dict[str, str]]:
        return SCENARIOS

    # ------------------------------------------------------------------ demo actions
    @app.post("/api/reset")
    def reset() -> dict[str, Any]:
        try:
            rt.crm.reset()
        except CrmError as exc:
            raise HTTPException(502, f"CRM not reachable: {exc}") from exc
        rt.store.reset()
        if rt.sim:
            rt.sim.reset()
        rt.events.clear()
        rt.log("info", "Reset: CRM reseeded with 8 fictional accounts, orchestrator state cleared")
        return {"result": "reset"}

    @app.post("/api/campaign")
    def campaign(body: CampaignUIIn) -> dict[str, Any]:
        use_clock = body.demo_clock and rt.gw.mode == "simulated"
        return run_campaign(CampaignIn(account_ids=body.account_ids, now=DEMO_NOW if use_clock else None))

    @app.post("/api/simulate")
    def simulate(body: SimulateIn) -> dict[str, Any]:
        if body.scenario not in {s["id"] for s in SCENARIOS}:
            raise HTTPException(422, "unknown scenario")
        if rt.gw.mode != "simulated":
            raise HTTPException(409, "Switch to SIMULATED mode to run scripted scenarios.")
        rt.sim.pending_scenario[body.account_id] = body.scenario
        rt.log("info", f"Simulating scenario '{body.scenario}' on {body.account_id}")
        return run_campaign(CampaignIn(account_ids=[body.account_id], cycle=f"sim-{ts()}", now=DEMO_NOW))

    @app.post("/api/crm/failure")
    def crm_failure(body: FailureIn) -> dict[str, Any]:
        if body.mode not in {"none", "error", "timeout"}:
            raise HTTPException(422, "mode must be none|error|timeout")
        try:
            out = rt.crm.set_failure(body.mode)
        except CrmError as exc:
            raise HTTPException(502, str(exc)) from exc
        rt.log("warn" if body.mode != "none" else "ok", f"CRM failure mode set to '{body.mode}'")
        return out

    @app.post("/api/outage-scenario")
    def outage_scenario() -> dict[str, Any]:
        if rt.gw.mode != "simulated":
            raise HTTPException(409, "Run the outage scenario in SIMULATED mode.")
        rt.sim.pending_scenario["ACC-1001"] = "promise_firm"
        call = run_campaign(CampaignIn(account_ids=["ACC-1001"], cycle=f"outage-{ts()}", now=DEMO_NOW))
        rt.crm.set_failure("error")  # break the CRM after reading the account, before the result comes back
        rt.log("warn", "Outage scenario: call placed, then CRM taken down. Wait for the webhook, then Restore + retry.")
        return {"call": call, "crm": "outage:error",
                "next": "Wait ~5s: the call shows crm_sync_failed and the outbox has a pending item. Then press Restore CRM + retry outbox."}

    @app.post("/api/crm/restore-and-retry")
    def restore_and_retry() -> dict[str, Any]:
        crm_failure(FailureIn(mode="none"))
        return retry_outbox()

    @app.post("/api/outbox/retry")
    def outbox_retry() -> dict[str, Any]:
        return retry_outbox()

    # ------------------------------------------------------------------ live CALL-E
    @app.post("/api/mode")
    def set_mode(body: ModeIn) -> dict[str, Any]:
        if body.mode == "simulated":
            rt.gw = ensure_sim()
        elif body.mode == "live":
            if rt.live is None:
                raise HTTPException(409, "Add your CALL-E API key first (step 1 of 'Call my phone').")
            rt.gw = rt.live
        else:
            raise HTTPException(422, "mode must be simulated|live")
        rt.log("info", f"CALL-E mode is now {rt.gw.mode.upper()}")
        return status()

    @app.post("/api/live/key")
    def set_key(body: KeyIn) -> dict[str, Any]:
        key = body.api_key.strip()
        if len(key) < 10:
            raise HTTPException(422, "That doesn't look like an API key.")
        try:
            allowed = set(getattr(rt.live, "allowed", set())) | {
                p.strip() for p in os.environ.get("CALLE_ALLOWED_PHONES", "").split(",") if p.strip()}
            rt.live = LiveCalleGateway(key, allowed)
        except ImportError as exc:
            raise HTTPException(500, "The calle-ai package is not installed. Run ./setup.sh again.") from exc
        rt.api_key = key
        check = rt.live.check_key()
        rt.log("ok" if check["ok"] else "error", f"CALL-E API key saved in memory: {check['detail']}")
        return check

    @app.post("/api/live/test-key")
    def test_key() -> dict[str, Any]:
        if rt.live is None:
            raise HTTPException(409, "No API key yet.")
        return rt.live.check_key()

    @app.post("/api/live/call-me")
    def call_me(body: CallMeIn) -> dict[str, Any]:
        if not body.consent:
            raise HTTPException(400, "Tick the box confirming this is your own phone.")
        phone = body.phone.replace(" ", "").replace("-", "")
        error = validate_phone(phone, body.region)
        if error:
            raise HTTPException(422, error)
        if rt.live is None:
            raise HTTPException(409, "Add your CALL-E API key first (step 1).")
        rt.gw = rt.live
        rt.live.allowed.add(phone)
        try:
            rt.crm.set_contact(body.account_id, {"phone_e164": phone, "region": body.region,
                                                 "locale": body.locale, "timezone": body.timezone})
        except CrmError as exc:
            raise HTTPException(502, f"CRM not reachable: {exc}") from exc
        rt.log("warn", f"LIVE call requested to {agent_config.mask_phone(phone)} as {body.account_id}")
        if body.region in UNLISTED_CALLING_CODES:
            rt.log("warn", f"{body.region} is not on CALL-E's published region list; CALL-E may reject this call")
        result = run_campaign(CampaignIn(account_ids=[body.account_id], cycle=f"live-{ts()}"))
        row = result["results"][0]
        if row["result"] != "submitted":
            hint = (f" ({body.region} is not on CALL-E's published region list: CALL-E suggests a SIP integration "
                    "for unlisted destinations.)") if body.region in UNLISTED_CALLING_CODES else ""
            raise HTTPException(409, f"Call not placed: {row.get('reason') or row['result']}: {row.get('detail', '')}{hint}")
        return {"call_id": row["call_id"], "mode": "live",
                "next": "Answer your phone. This page polls CALL-E every 5 seconds until the call is finished."}

    # ------------------------------------------------------------------ call detail
    @app.get("/api/calls/{call_id}/detail")
    def call_detail(call_id: str) -> dict[str, Any]:
        req = rt.store.get_by_call_id(call_id)
        if req is None:
            raise HTTPException(404, "unknown call id")
        snapshot, error = None, None
        try:
            snapshot = rt.gw.get_call(call_id)
        except GatewayError as exc:
            error = str(exc)
        turns: list[dict[str, Any]] = []
        if snapshot:
            for rcp in snapshot.get("recipients") or []:
                for att in rcp.get("attempts") or []:
                    turns += att.get("transcript_turns") or []
            if not turns:
                turns = snapshot.get("transcript") or []
        interaction = None
        for it in crm_try(rt.crm.list_interactions, []):
            if it["call_id"] == call_id:
                interaction = it
        request = json.loads(req["request_json"]) if req.get("request_json") else None
        return {
            "orchestrator": {k: req[k] for k in ("account_id", "call_id", "state", "outcome", "crm_status", "detail")},
            "calle_status": snapshot.get("status") if snapshot else None,
            "calle_error": error,
            "summary": snapshot.get("summary") if snapshot else None,
            "structured_result": extract_result(snapshot) if snapshot else None,
            "transcript": [{"speaker": t.get("speaker"), "text": t.get("text")} for t in turns],
            "crm_interaction": interaction,
            "request_sent": request,
        }

    # ------------------------------------------------------------------ troubleshooting
    @app.get("/api/troubleshoot")
    def troubleshoot() -> dict[str, Any]:
        checks: list[dict[str, str]] = []

        def add(name: str, state: str, detail: str, fix: str = "") -> None:
            checks.append({"check": name, "state": state, "detail": detail, "fix": fix})

        add("Orchestrator", "ok", f"Running on Python {platform.python_version()}")
        try:
            import calle  # noqa: F401
            add("calle-ai SDK", "ok", "Installed (needed only for live calls)")
        except ImportError:
            add("calle-ai SDK", "fail", "Not installed", "Run ./setup.sh again.")
        crm_mode = crm_try(rt.crm.get_failure, "unreachable")
        if crm_mode == "unreachable":
            add("Mock CRM :8001", "fail", "Not reachable", "Start the services with ./run.sh (or ./demo.sh).")
        elif crm_mode != "none":
            add("Mock CRM :8001", "warn", f"Reachable but in injected outage mode '{crm_mode}'",
                "Press 'Restore CRM + retry outbox' on the Demo tab.")
        else:
            add("Mock CRM :8001", "ok", "Reachable and healthy")
        add("CALL-E mode", "ok", rt.gw.mode.upper(),
            "" if rt.gw.mode == "simulated" else "Live mode places real calls to allowlisted numbers only.")
        if rt.live is None:
            add("CALL-E API key", "warn", "Not set (fine for simulated mode)",
                "Create a key at https://dashboard.heycall-e.com/account/api-keys and paste it in 'Call my phone'.")
        else:
            chk = rt.live.check_key()
            add("CALL-E API key + network", "ok" if chk["ok"] else "fail", chk["detail"],
                "" if chk["ok"] else "Check the key, your internet connection, and that api.heycall-e.com isn't blocked.")
        wh = rt.webhook_url()
        if rt.gw.mode == "live" and not wh:
            add("Webhook", "ok", "Polling mode: no public URL, the UI polls /calls/{id}/sync every 5s",
                "Optional: run 'ngrok http 8000' and set PUBLIC_WEBHOOK_URL=https://<id>.ngrok.app/calle/webhook in .env.")
        else:
            last = rt.store.last_webhook()
            add("Webhook", "ok", f"URL: {wh}. Last received: {last['received_at'] + ' (' + last['type'] + ')' if last else 'none yet'}")
        pending = [o for o in rt.store.outbox_all() if o["state"] == "pending"]
        dead = [o for o in rt.store.outbox_all() if o["state"] == "dead_letter"]
        add("CRM outbox", "fail" if dead else ("warn" if pending else "ok"),
            f"{len(pending)} pending, {len(dead)} dead-letter",
            "Restore the CRM, then 'Retry outbox'." if pending else ("Dead letters need a data fix in the CRM." if dead else ""))
        stuck = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        for c in rt.store.list_requests():
            if c["state"] == "submitted" and c["updated_at"] and datetime.fromisoformat(c["updated_at"]) < cutoff:
                stuck.append(c["call_id"])
        add("Calls waiting > 10 min", "warn" if stuck else "ok", ", ".join(stuck) or "none",
            "Open the call in Results and press 'Sync from CALL-E'." if stuck else "")
        errors = [e for e in rt.events if e["level"] == "error"][:5]
        return {"checks": checks, "recent_errors": errors}

    # ------------------------------------------------------------------ docs for the Learn page
    def doc_files() -> dict[str, Path]:
        files = {"README": ROOT / "README.md"}
        for p in sorted((ROOT / "docs").glob("*.md")):
            files[p.stem] = p
        return files

    @app.get("/api/docs")
    def list_docs() -> list[str]:
        return list(doc_files())

    @app.get("/api/docs/{name}", response_class=PlainTextResponse)
    def get_doc(name: str) -> str:
        files = doc_files()
        if name not in files:
            raise HTTPException(404, "unknown doc")
        return files[name].read_text(encoding="utf-8")

