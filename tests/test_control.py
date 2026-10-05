"""Control center API (/api/*) and the live CALL-E path.

Live tests use the official calle-ai SDK against a fake CALL-E API (httpx.MockTransport),
so the request/response handling is exercised without placing a real call.
"""

from datetime import datetime, timezone

import httpx
import pytest

from app.orchestrator.calle_gateway import LiveCalleGateway


def rt(env):
    return env.orch.app.state.rt


# ---------------------------------------------------------------- pages + status
def test_pages_and_status(env):
    assert "Solaria Control Center" in env.orch.get("/").text
    assert "Solaria Project Guide" in env.orch.get("/learn").text
    st = env.orch.get("/api/status").json()
    assert st["mode"] == "simulated" and st["crm"] == "healthy" and st["regions"]["MX"] == "+52"
    docs = env.orch.get("/api/docs").json()
    assert "README" in docs and "03-integration" in docs
    assert "Field mapping" in env.orch.get("/api/docs/03-integration").text
    assert env.orch.get("/api/docs/../../etc/passwd").status_code == 404


def test_reset_campaign_and_overview(env):
    assert env.orch.post("/api/reset").json() == {"result": "reset"}
    res = env.orch.post("/api/campaign", json={}).json()
    kinds = sorted(r["result"] for r in res["results"])
    assert kinds.count("submitted") == 6 and kinds.count("blocked") == 2
    ov = env.orch.get("/api/overview").json()
    assert len(ov["calls"]) == 8 and len(ov["accounts"]) == 8
    assert any("blocked before CALL-E" in e["message"] for e in ov["events"])


def test_simulate_specific_scenario(env):
    res = env.orch.post("/api/simulate", json={"scenario": "human_requested"}).json()
    call_id = res["results"][0]["call_id"]
    r, _ = env.deliver(call_id)  # scenario chosen in the UI, not the default for ACC-1001
    assert r.json()["outcome"] == "human_requested"
    detail = env.orch.get(f"/api/calls/{call_id}/detail").json()
    assert detail["structured_result"]["outcome"] == "human_requested"
    assert detail["transcript"][0]["speaker"] == "bot"
    assert detail["crm_interaction"]["new_status"] == "callback_requested"
    assert "result_schema" in detail["request_sent"]


def test_outage_scenario_then_restore(env):
    out = env.orch.post("/api/outage-scenario").json()
    call_id = out["call"]["results"][0]["call_id"]
    assert env.orch.get("/api/status").json()["crm"] == "outage:error"
    r, _ = env.deliver(call_id)
    assert r.status_code == 202 and r.json()["crm_sync"] == "pending_retry"
    checks = {c["check"]: c for c in env.orch.get("/api/troubleshoot").json()["checks"]}
    assert checks["Mock CRM :8001"]["state"] == "warn" and checks["CRM outbox"]["state"] == "warn"
    retried = env.orch.post("/api/crm/restore-and-retry").json()["retried"]
    assert [x["crm_sync"] for x in retried] == ["synced"]
    assert env.orch.get("/api/status").json()["crm"] == "healthy"


def test_mode_switch_requires_key(env):
    r = env.orch.post("/api/mode", json={"mode": "live"})
    assert r.status_code == 409 and "API key" in r.json()["detail"]


# ---------------------------------------------------------------- live path (fake CALL-E)
class FakeCalle:
    """Minimal stand-in for api.heycall-e.com with the response shapes the SDK expects."""

    def __init__(self):
        self.created = []
        self.reads = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != "Bearer good-key":
            return httpx.Response(401, json={"error": {"code": "unauthorized", "message": "Invalid API key"}})
        if request.method == "POST" and request.url.path == "/v1/calls":
            import json
            if json.loads(request.content)["recipients"][0].get("region") in {"AR", "CN"}:
                return httpx.Response(422, json={"error": {"code": "unsupported_region", "message": "Region is not supported"}})
            self.created.append({"body": json.loads(request.content), "idem": request.headers.get("idempotency-key")})
            return httpx.Response(201, json={"id": "call_live_1", "object": "call", "status": "queued"})
        if request.method == "GET" and request.url.path == "/v1/calls/call_live_1":
            self.reads += 1
            if self.reads == 1:
                return httpx.Response(200, json={"id": "call_live_1", "status": "in_progress", "recipients": []})
            return httpx.Response(200, json={
                "id": "call_live_1", "status": "completed", "summary": "Holder promised to pay Friday.",
                "structured_result": None,
                "recipients": [{"id": "r1", "status": "completed", "structured_result": {
                    "right_party": "confirmed", "outcome": "promise_to_pay", "promise_date": "2026-10-09",
                    "promise_certainty": "firm", "needs_human": "no", "outcome_evidence": "El viernes pago."},
                    "attempts": [{"id": "a1", "status": "completed", "transcript_turns": [
                        {"speaker": "bot", "text": "Hola"}, {"speaker": "user", "text": "El viernes pago."}]}]}],
            })
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "Call not found"}})


def fake_gateway(key="good-key"):
    fake = FakeCalle()
    client = httpx.Client(base_url="https://fake-calle", transport=httpx.MockTransport(fake.handler),
                          headers={"Authorization": f"Bearer {key}"})
    return LiveCalleGateway(key, set(), http_client=client), fake


def tz_where_it_is_noon() -> str:
    offset = (12 - datetime.now(timezone.utc).hour) % 24
    offset = offset - 24 if offset > 14 else offset
    return f"Etc/GMT{'-' if offset > 0 else '+'}{abs(offset)}"  # Etc/GMT-5 means UTC+5


def test_key_check_classifies_responses():
    good, _ = fake_gateway("good-key")
    bad, _ = fake_gateway("bad-key")
    assert good.check_key()["ok"] is True
    res = bad.check_key()
    assert res["ok"] is False and "401" in res["detail"]


def test_live_allowlist_refuses_unknown_numbers():
    gw, fake = fake_gateway()
    from app.orchestrator.calle_gateway import GatewayError
    with pytest.raises(GatewayError, match="allowlist"):
        gw.create_call({"task": "x", "recipients": [{"phones": ["+525511112222"]}]}, "k1")
    assert fake.created == []


def test_call_me_validation(env):
    base = {"phone": "+525512345678", "region": "MX", "locale": "es-MX", "timezone": "America/Mexico_City"}
    assert env.orch.post("/api/live/call-me", json={**base, "consent": False}).status_code == 400
    assert env.orch.post("/api/live/call-me", json={**base, "phone": "+5255123", "consent": True}).status_code == 422
    assert env.orch.post("/api/live/call-me", json={**base, "region": "AR", "consent": True}).status_code == 422
    r = env.orch.post("/api/live/call-me", json={**base, "consent": True})
    assert r.status_code == 409 and "API key" in r.json()["detail"]


def test_call_me_end_to_end_with_fake_calle(env):
    gw, fake = fake_gateway()
    rt(env).live, rt(env).api_key = gw, "good-key"
    r = env.orch.post("/api/live/call-me", json={
        "phone": "+52 55 1234 5678", "region": "MX", "locale": "es-MX",
        "timezone": tz_where_it_is_noon(), "consent": True})
    assert r.status_code == 200, r.text
    call_id = r.json()["call_id"]
    assert rt(env).gw.mode == "live"

    sent = fake.created[0]
    assert sent["body"]["recipients"] == [{"phones": ["+525512345678"], "region": "MX", "locale": "es-MX"}]
    assert sent["idem"].startswith("solaria-reminder-live-")
    assert "webhook_url" not in sent["body"]  # no public URL -> polling

    first = env.orch.post(f"/calls/{call_id}/sync")
    assert first.status_code == 202 and first.json()["status"] == "in_progress"
    done = env.orch.post(f"/calls/{call_id}/sync").json()
    assert done["result"] == "processed" and done["crm_status"] == "promise_to_pay"
    interaction = next(i for i in env.crm.get("/interactions").json() if i["call_id"] == call_id)
    assert interaction["source"] == "calle_live"
    detail = env.orch.get(f"/api/calls/{call_id}/detail").json()
    assert detail["transcript"][1]["text"] == "El viernes pago."


def test_country_dropdown_includes_argentina_china_singapore(env):
    countries = {c["code"]: c for c in env.orch.get("/api/status").json()["countries"]}
    assert countries["SG"]["supported"] is True and countries["SG"]["calling_code"] == "+65"
    assert countries["AR"] == {"code": "AR", "name": "Argentina", "calling_code": "+54", "supported": False}
    assert countries["CN"] == {"code": "CN", "name": "China", "calling_code": "+86", "supported": False}


@pytest.mark.parametrize("phone,region,ok", [
    ("+5491123456789", "AR", True), ("+8613812345678", "CN", True), ("+6581234567", "SG", True),
    ("+525512345678", "AR", False), ("+5491123456789", "ZZ", False),
])
def test_phone_validation_new_countries(phone, region, ok):
    from app.orchestrator.guards import validate_phone
    assert (validate_phone(phone, region) is None) is ok


def test_unlisted_country_rejection_is_reported_not_hidden(env):
    gw, fake = fake_gateway()
    rt(env).live, rt(env).api_key = gw, "good-key"
    r = env.orch.post("/api/live/call-me", json={
        "phone": "+5491123456789", "region": "AR", "locale": "es-AR",
        "timezone": tz_where_it_is_noon(), "consent": True})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "submit_failed" in detail and "Region is not supported" in detail and "SIP" in detail
    assert fake.created == []
    events = env.orch.get("/api/overview").json()["events"]
    assert any("not on CALL-E's published region list" in e["message"] for e in events)
