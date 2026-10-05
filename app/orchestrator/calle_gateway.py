"""CALL-E access behind one interface, in two modes.

LIVE (CALLE_MODE=live)       Real CALL-E Developer API via the official `calle-ai`
                             SDK (0.7.0). Places REAL phone calls.
SIMULATED (default)          Local stand-in that accepts the identical request
                             body, then produces a terminal call snapshot and an
                             unsigned webhook in the documented CALL-E shape
                             (call.completed / call.failed /
                             call.result_validation_failed). What happens *on
                             the phone* and the extracted structured_result come
                             from scripted fixtures in app/simulator/scenarios.

Everything downstream (webhook receiver, re-fetch, business rules, CRM write)
is the same code in both modes.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "simulator" / "scenarios"


class GatewayError(Exception):
    """CALL-E could not be reached or rejected the request."""


class CalleGateway(Protocol):
    mode: str

    def create_call(self, body: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...

    def get_call(self, call_id: str) -> dict[str, Any]: ...


class LiveCalleGateway:
    mode = "live"

    def __init__(self, api_key: str, allowed_phones: set[str]):
        from calle import CalleClient  # imported lazily so simulated mode needs no key

        self._client = CalleClient(api_key=api_key)
        self._allowed = allowed_phones

    def create_call(self, body: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        phones = {p for r in body.get("recipients", []) for p in r["phones"]}
        # Safety: a live call is only placed to numbers explicitly authorised for testing/pilot.
        if not phones or not phones <= self._allowed:
            raise GatewayError("Refusing live call: recipient not in CALLE_ALLOWED_PHONES allowlist.")
        from calle import CalleAPIError, CalleConnectionError, CalleTimeoutError

        try:
            return self._client.calls.create(idempotency_key=idempotency_key, **body)
        except (CalleAPIError, CalleConnectionError, CalleTimeoutError) as exc:
            raise GatewayError(f"CALL-E create failed: {exc}") from exc

    def get_call(self, call_id: str) -> dict[str, Any]:
        from calle import CalleAPIError, CalleConnectionError, CalleTimeoutError

        try:
            return self._client.calls.get(call_id)
        except (CalleAPIError, CalleConnectionError, CalleTimeoutError) as exc:
            raise GatewayError(f"CALL-E get failed: {exc}") from exc


class SimulatedCalleGateway:
    """SIMULATED CALL-E. Never dials anything."""

    mode = "simulated"

    def __init__(self, webhook_url: str | None = None, delay_seconds: float = 2.0, auto_deliver: bool = True):
        self.webhook_url = webhook_url
        self.delay = delay_seconds
        self.auto_deliver = auto_deliver
        self._calls: dict[str, dict[str, Any]] = {}
        self._by_key: dict[str, str] = {}
        self._lock = threading.Lock()
        self.scenario_map: dict[str, str] = json.loads((SCENARIO_DIR / "_account_map.json").read_text())
        self.unavailable = False  # fault injection: CALL-E API down

    def create_call(self, body: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        if self.unavailable:
            raise GatewayError("SIMULATED CALL-E API unavailable")
        with self._lock:
            if idempotency_key in self._by_key:  # same semantics as the real Idempotency-Key header
                return self._calls[self._by_key[idempotency_key]]
            call_id = f"call_sim_{uuid.uuid4().hex[:12]}"
            snapshot = {
                "id": call_id,
                "object": "call",
                "status": "queued",
                "task": body["task"],
                "metadata": body.get("metadata", {}),
                "created_at": _now(),
                "completed_at": None,
                "structured_result": None,
                "simulated": True,
                "recipients": [
                    {"id": "rcp_1", **body["recipients"][0], "status": "queued", "structured_result": None, "attempts": []}
                ],
            }
            self._calls[call_id] = snapshot
            self._by_key[idempotency_key] = call_id
        if self.auto_deliver and self.webhook_url:
            threading.Thread(target=self._deliver_later, args=(call_id,), daemon=True).start()
        return snapshot

    def get_call(self, call_id: str) -> dict[str, Any]:
        if self.unavailable:
            raise GatewayError("SIMULATED CALL-E API unavailable")
        if call_id not in self._calls:
            raise GatewayError(f"call {call_id} not found")
        return json.loads(json.dumps(self._calls[call_id]))

    # --- simulation of the phone call itself -------------------------------------------
    def complete(self, call_id: str, scenario: str | None = None) -> dict[str, Any]:
        """Finish the call using a scripted scenario and return the webhook event CALL-E would send."""
        snap = self._calls[call_id]
        account_id = snap["metadata"].get("account_id", "")
        name = scenario or self.scenario_map.get(account_id, "promise_firm")
        sc = json.loads((SCENARIO_DIR / f"{name}.json").read_text(encoding="utf-8"))
        rcp = snap["recipients"][0]
        snap.update(
            status=sc["status"],
            completed_at=_now(),
            summary=sc.get("summary"),
            evidence=sc.get("evidence", []),
            task_completed=sc.get("task_completed"),
            structured_result=sc.get("structured_result"),
            simulated_scenario=name,
        )
        rcp.update(
            status=sc["status"],
            structured_result=sc.get("structured_result"),
            summary=sc.get("summary"),
            attempts=[
                {
                    "id": "att_1",
                    "phone": rcp["phones"][0],
                    "status": sc.get("attempt_status", sc["status"]),
                    "failure_code": sc.get("failure_code"),
                    "transcript_turns": sc.get("transcript_turns", []),
                }
            ],
        )
        return {"id": f"evt_sim_{uuid.uuid4().hex[:12]}", "type": sc["event_type"], "created_at": _now(), "data": self.get_call(call_id)}

    def _deliver_later(self, call_id: str) -> None:
        time.sleep(self.delay)
        event = self.complete(call_id)
        try:
            httpx.post(self.webhook_url, json=event, headers={"CALL-E-Event-Id": event["id"]}, timeout=30)
        except httpx.HTTPError:
            pass  # like the real service: delivery may fail; /calls/{id}/sync is the fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_gateway() -> CalleGateway:
    mode = os.environ.get("CALLE_MODE", "simulated")
    if mode == "live":
        key = os.environ.get("CALLE_API_KEY")
        if not key:
            raise RuntimeError("CALLE_MODE=live requires CALLE_API_KEY")
        allowed = {p.strip() for p in os.environ.get("CALLE_ALLOWED_PHONES", "").split(",") if p.strip()}
        return LiveCalleGateway(key, allowed)
    return SimulatedCalleGateway(
        webhook_url=os.environ.get("SIM_WEBHOOK_URL", "http://127.0.0.1:8000/calle/webhook"),
        delay_seconds=float(os.environ.get("SIM_DELAY_SECONDS", "2")),
    )
