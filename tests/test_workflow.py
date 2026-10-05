"""End-to-end tests: CRM -> orchestrator -> (simulated) CALL-E -> webhook -> rules -> CRM.

T1-T4 are the four tests required by the assignment; the rest are edge cases.
"""

from tests.conftest import NOON_CDMX


def submitted_call_id(resp, account_id):
    row = next(r for r in resp.json()["results"] if r["account_id"] == account_id)
    assert row["result"] == "submitted", row
    return row["call_id"]


# ---------------------------------------------------------------- T1 normal interaction
def test_t1_normal_promise_to_pay(env):
    resp = env.campaign("ACC-1001")
    call_id = submitted_call_id(resp, "ACC-1001")

    # Request sent to CALL-E is correctly configured for Mexico.
    snap = env.gateway.get_call(call_id)
    assert snap["recipients"][0]["region"] == "MX" and snap["recipients"][0]["locale"] == "es-MX"
    assert snap["metadata"]["account_id"] == "ACC-1001"
    assert "2,450.00 MXN" in snap["task"] and "SOL-7781-1001" in snap["task"]

    r, _ = env.deliver(call_id)
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == "processed" and body["crm_sync"] == "synced"
    assert body["crm_confirmation"]["result"] == "created"  # success = CRM's own confirmation

    acc = env.account("ACC-1001")
    assert acc["status"] == "promise_to_pay"
    [task] = env.tasks("ACC-1001")
    assert task["type"] == "verify_payment" and task["due_date"] == "2026-10-10"
    interaction = next(i for i in env.crm.get("/interactions").json() if i["call_id"] == call_id)
    assert interaction["promise_date"] == "2026-10-09" and interaction["payment_channel"] == "spei_transfer"
    assert env.orch.get("/notifications").json()[0]["channel"] == "sms"


# ---------------------------------------------------------------- T2 incomplete / ambiguous
def test_t2_ambiguous_promise_goes_to_review_not_ptp(env):
    call_id = submitted_call_id(env.campaign("ACC-1002"), "ACC-1002")
    r, _ = env.deliver(call_id)
    body = r.json()
    assert body["outcome"] == "promise_to_pay"
    assert body["crm_status"] == "needs_review"
    assert "promise_without_specific_date" in body["review_reasons"]
    assert "promise_certainty_tentative" in body["review_reasons"]
    assert env.account("ACC-1002")["status"] == "needs_review"
    [task] = env.tasks("ACC-1002")
    assert task["type"] == "confirm_promise" and task["team"] == "collections_agents"
    assert env.orch.get("/notifications").json() == []  # no payment link for a non-promise


def test_t2b_missing_phone_blocks_call_and_creates_data_task(env):
    resp = env.campaign("ACC-1004")
    row = resp.json()["results"][0]
    assert row == {"account_id": "ACC-1004", "result": "blocked", "reason": "missing_phone",
                   "detail": "Account has no phone number on file."}
    assert env.gateway._calls == {}  # nothing was sent to CALL-E
    assert env.account("ACC-1004")["status"] == "contact_data_missing"
    assert env.tasks("ACC-1004")[0]["type"] == "fix_contact_data"


# ---------------------------------------------------------------- T3 integration failure
def test_t3_crm_down_is_detected_not_reported_as_success_then_recovers(env):
    call_id = submitted_call_id(env.campaign("ACC-1001"), "ACC-1001")
    env.crm.post("/admin/failure", json={"mode": "error"})

    r, event = env.deliver(call_id)
    assert r.status_code == 202
    body = r.json()
    assert body["result"] == "received_crm_sync_failed" and body["crm_sync"] == "pending_retry"
    assert "503" in body["error"]
    assert env.call_row("ACC-1001")["state"] == "crm_sync_failed"
    assert env.orch.get("/outbox").json()[0]["state"] == "pending"

    env.crm.post("/admin/failure", json={"mode": "none"})
    assert env.account("ACC-1001")["status"] == "upcoming_due"  # CRM really was not updated

    retry = env.orch.post("/outbox/retry").json()["retried"]
    assert retry[0]["crm_sync"] == "synced"
    assert env.account("ACC-1001")["status"] == "promise_to_pay"
    assert env.call_row("ACC-1001")["state"] == "synced"

    # CALL-E redelivers the same event (at-least-once): no duplicate CRM write.
    r2 = env.orch.post("/calle/webhook", json=event, headers={"CALL-E-Event-Id": event["id"]})
    assert r2.json()["result"] == "duplicate"
    assert len(env.tasks("ACC-1001")) == 1


def test_t3b_calle_api_unreachable_on_verify(env):
    call_id = submitted_call_id(env.campaign("ACC-1001"), "ACC-1001")
    event = env.gateway.complete(call_id)
    env.gateway.unavailable = True
    r = env.orch.post("/calle/webhook", json=event, headers={"CALL-E-Event-Id": event["id"]})
    assert r.status_code == 503 and r.json()["result"] == "verify_failed"
    assert env.account("ACC-1001")["status"] == "upcoming_due"
    env.gateway.unavailable = False
    assert env.orch.post(f"/calls/{call_id}/sync").json()["result"] == "processed"  # polling fallback


def test_t3c_crm_read_failure_aborts_campaign_without_calling(env):
    env.crm.post("/admin/failure", json={"mode": "error"})
    r = env.campaign("ACC-1001")
    assert r.status_code == 502
    assert env.gateway._calls == {}


def test_t3d_calle_create_failure_is_reported(env):
    env.gateway.unavailable = True
    row = env.campaign("ACC-1001").json()["results"][0]
    assert row["result"] == "submit_failed"
    assert env.call_row("ACC-1001")["state"] == "submit_failed"


# ---------------------------------------------------------------- T4 customer exception
def test_t4_customer_asks_for_human(env):
    call_id = submitted_call_id(env.campaign("ACC-1003"), "ACC-1003")
    body = env.deliver(call_id)[0].json()
    assert body["outcome"] == "human_requested" and body["crm_status"] == "callback_requested"
    [task] = env.tasks("ACC-1003")
    assert task["type"] == "human_callback" and task["priority"] == "high"
    assert "después de las 5" in task["description"]


def test_t4b_wrong_party_no_debt_outcome(env):
    call_id = submitted_call_id(env.campaign("ACC-1005"), "ACC-1005")
    body = env.deliver(call_id)[0].json()
    assert body["crm_status"] == "wrong_party_contact"
    transcript = " ".join(t["text"] for t in env.gateway.get_call(call_id)["recipients"][0]["attempts"][0]["transcript_turns"])
    assert "2,100" not in transcript and "pago" not in transcript.lower()


# ---------------------------------------------------------------- other edge cases
def test_already_paid_goes_to_finance_not_marked_paid(env):
    call_id = submitted_call_id(env.campaign("ACC-1006"), "ACC-1006")
    assert env.deliver(call_id)[0].json()["crm_status"] == "paid_claimed"
    assert env.tasks("ACC-1006")[0]["team"] == "finance"


def test_no_answer_call_failed(env):
    call_id = submitted_call_id(env.campaign("ACC-1007"), "ACC-1007")
    r, event = env.deliver(call_id)
    assert event["type"] == "call.failed"
    assert r.json()["crm_status"] == "no_contact"


def test_result_validation_failed_needs_review(env):
    call_id = submitted_call_id(env.campaign("ACC-1001"), "ACC-1001")
    r, event = env.deliver(call_id, scenario="result_validation_failed")
    assert event["type"] == "call.result_validation_failed"
    assert r.json()["crm_status"] == "needs_review"


def test_do_not_call_and_calling_window(env):
    assert env.campaign("ACC-1008").json()["results"][0]["reason"] == "do_not_call"
    # 22:00 in Mexico City is outside the 08:00-21:00 window.
    late = env.campaign("ACC-1001", now="2026-10-06T04:00:00+00:00").json()["results"][0]
    assert late["reason"] == "outside_calling_window"
    assert env.gateway._calls == {}


def test_campaign_rerun_does_not_call_twice(env):
    call_id = submitted_call_id(env.campaign("ACC-1001"), "ACC-1001")
    again = env.campaign("ACC-1001").json()["results"][0]
    assert again == {"account_id": "ACC-1001", "result": "skipped_already_called", "call_id": call_id}
    assert len(env.gateway._calls) == 1


def test_webhook_consistency_checks(env):
    call_id = submitted_call_id(env.campaign("ACC-1001"), "ACC-1001")
    event = env.gateway.complete(call_id)
    assert env.orch.post("/calle/webhook", json=event, headers={"CALL-E-Event-Id": "evt_other"}).status_code == 400
    forged = {**event, "data": {**event["data"], "id": "call_not_ours"}}
    r = env.orch.post("/calle/webhook", json=forged, headers={"CALL-E-Event-Id": forged["id"]})
    assert r.status_code == 202 and r.json()["result"] == "ignored"


def test_forged_webhook_body_is_not_trusted(env):
    """The receiver re-fetches the call; a tampered webhook body cannot change the outcome."""
    call_id = submitted_call_id(env.campaign("ACC-1002"), "ACC-1002")
    event = env.gateway.complete(call_id)
    event["data"]["structured_result"] = {**event["data"]["structured_result"], "promise_date": "2026-10-09",
                                          "promise_certainty": "firm"}
    r = env.orch.post("/calle/webhook", json=event, headers={"CALL-E-Event-Id": event["id"]})
    assert r.json()["crm_status"] == "needs_review"


def test_task_text_contains_safety_rules():
    from app.orchestrator.agent_config import build_task
    import json, pathlib
    acc = json.loads(pathlib.Path("data/seed_accounts.json").read_text())[0]
    task = build_task(acc, "2026-10-05")
    for rule in ["virtual assistant", "do NOT mention the loan", "NEVER: threaten", "claim to be a human"]:
        assert rule in task
