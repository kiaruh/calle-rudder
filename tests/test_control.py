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


def test_learn_ai_rudder_tab_and_video(env):
    assert 'data-tab="rudder"' in env.orch.get("/").text
    assert env.orch.get("/rudder", follow_redirects=False).headers["location"] == "/rudder/"
    guide = env.orch.get("/rudder/")
    assert guide.status_code == 200 and "Learn AI Rudder" in guide.text
    video = env.orch.get("/rudder/ai-rudder-explainer.mp4", headers={"Range": "bytes=0-99"})
    assert video.status_code == 206 and video.headers["content-type"] == "video/mp4" and len(video.content) == 100
    assert env.orch.get("/rudder/video/player.html").status_code == 200


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


# ---------------------------------------------------------------- API key handling
def patch_live_factory(monkeypatch):
    import app.orchestrator.control as control

    def factory(key, allowed):
        gw, _ = fake_gateway(key)
        gw.allowed = allowed
        return gw
    monkeypatch.setattr(control, "LiveCalleGateway", factory)


def test_pasted_text_is_refused_as_key(env, monkeypatch):
    patch_live_factory(monkeypatch)
    pasted = "What the orchestrator just did, newest first.  14:38:26 UTC CALL-E API key saved in memory"
    r = env.orch.post("/api/live/key", json={"api_key": pasted})
    assert r.status_code == 422 and "spaces or line breaks" in r.json()["detail"]
    assert env.orch.post("/api/live/key", json={"api_key": "short"}).status_code == 422
    assert env.orch.get("/api/status").json()["api_key_set"] is False


def test_good_key_saved_masked_and_rejected_key_keeps_previous(env, monkeypatch):
    patch_live_factory(monkeypatch)
    good = "good-key"  # the fake CALL-E accepts exactly this bearer token
    r = env.orch.post("/api/live/key", json={"api_key": "Bearer " + good + "-padding-to-20"})
    assert r.json()["rejected"] is True  # wrong token -> 401 from fake CALL-E, not saved
    assert env.orch.get("/api/status").json()["api_key_set"] is False

    import app.orchestrator.control as control
    monkeypatch.setattr(control, "clean_key", lambda raw: raw.strip())  # allow the short fake token
    ok = env.orch.post("/api/live/key", json={"api_key": good}).json()
    assert ok["ok"] is True and "recognised the key" in ok["detail"]
    assert env.orch.get("/api/status").json()["api_key_set"] is True

    bad = env.orch.post("/api/live/key", json={"api_key": "bad-key"}).json()
    assert bad["rejected"] is True and "previous key" in bad["detail"]
    assert rt(env).api_key == good  # the working key is still in use


# ---------------------------------------------------------------- public deployment (Netlify + Render)
def test_live_calls_need_passcode_when_configured(env, monkeypatch):
    monkeypatch.setenv("LIVE_PASSCODE", "s3cret")
    assert env.orch.get("/api/status").json()["live_locked"] is True
    for path, body in [("/api/live/key", {"api_key": "sk-x"}), ("/api/live/call-me", {"phone": "+525512345678"}),
                       ("/api/mode", {"mode": "live"})]:
        r = env.orch.post(path, json=body)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "live_passcode_required", path
        assert env.orch.post(path, json=body, headers={"x-live-passcode": "wrong"}).status_code == 401
    # Simulated mode never needs the passcode; the right passcode gets past the gate (then normal validation).
    assert env.orch.post("/api/mode", json={"mode": "simulated"}).status_code == 200
    assert env.orch.post("/api/mode", json={"mode": "live"}, headers={"x-live-passcode": "s3cret"}).status_code == 409


def test_live_calls_open_locally(env, monkeypatch):
    monkeypatch.delenv("LIVE_PASSCODE", raising=False)
    assert env.orch.get("/api/status").json()["live_locked"] is False
    assert env.orch.post("/api/mode", json={"mode": "live"}).status_code == 409  # no key yet, but not locked


def test_combined_app_mounts_crm_and_pages(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.combined import create_app
    for k in ("CRM_BASE_URL", "SIM_WEBHOOK_URL", "PUBLIC_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://calle-rudder-api.onrender.com")
    monkeypatch.setenv("CRM_DB", str(tmp_path / "crm.sqlite3"))
    monkeypatch.setenv("ORCH_DB", str(tmp_path / "orch.sqlite3"))
    import os
    c = TestClient(create_app())
    assert os.environ["CRM_BASE_URL"] == "http://127.0.0.1:10000/crm"
    assert os.environ["PUBLIC_WEBHOOK_URL"] == "https://calle-rudder-api.onrender.com/calle/webhook"
    assert len(c.get("/crm/accounts").json()) == 8
    crm_page = c.get("/crm/").text
    assert "act('admin/failure'" in crm_page and "act('/admin" not in crm_page
    assert "Solaria Control Center" in c.get("/").text and c.get("/rudder/").status_code == 200
