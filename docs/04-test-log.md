# 4. Test log

**Environment:** Python 3.11, FastAPI 0.115, `calle-ai` 0.7.0 SDK. CALL-E in **SIMULATED** mode: the
transcripts and extracted results are scripted. Everything else ran for real: the mock CRM is a separate
HTTP service, and the orchestrator's guards, webhook handling, re-fetch, rules, outbox and CRM writes were
all exercised. Command: `python3 -m pytest -v` and `python3 scripts/demo.py`.

## Required tests

| # | Scenario | Expected result | Actual result | Evidence | Improvement / next action |
|---|---|---|---|---|---|
| **T1** Normal | ACC-1001 confirms identity, "El viernes nueve hago la transferencia por SPEI" | CRM `promise_to_pay`; `verify_payment` task due 2026-10-10; SMS link queued; CRM confirms 201 | **Pass** (v1 and v2) | `test_t1_normal_promise_to_pay`; demo ACT 3-4 | Validate with a live CALL-E call that the extractor resolves "el viernes" → `2026-10-09` |
| **T2** Ambiguous | ACC-1002: "luego, cuando me paguen" → agent clarifies once → "a fin de mes, si me pagan a tiempo" | Not counted as a promise. `needs_review` + `confirm_promise` task for a human; no SMS | **v1: FAIL**, recorded as `promise_to_pay` (a false promise; the `verify_payment` task fell back to the original due date and an SMS link was queued). **v2: Pass** | `evidence/v1_test_run.txt` (`assert 'promise_to_pay' == 'needs_review'`); `evidence/v2_test_run.txt` | **Fixed**: promise rule (specific ISO date + `firm` + ≤ due+7d) |
| **T2b** Missing info | ACC-1004 has no phone | No call to CALL-E; CRM `contact_data_missing` + `fix_contact_data` task | **Pass** | `test_t2b_missing_phone_...`; demo ACT 2 | Also add a phone-format check at CRM data entry |
| **T3** Integration failure | CRM returns 503 when the call result arrives | Failure detected; **no** success reported; result kept; delivered once CRM recovers | **v1: FAIL**: webhook answered **200 "synced"** while the CRM write had failed, so the result was lost silently. **v2: Pass**: 202 `pending_retry`, state `crm_sync_failed`, outbox `pending`; retry → CRM 201; redelivery → `duplicate`, still 1 task | v1/v2 evidence files; demo ACT 5-6 | **Fixed**: outbox + honest status. Next: automatic retry worker + alert when the outbox is older than 15 min |
| **T4** Customer exception | ACC-1003: "Prefiero hablar con una persona" → "mañana después de las cinco" | `callback_requested`; **high**-priority `human_callback` task with the preferred time | **Pass** | `test_t4_customer_asks_for_human` | Needs a real hand-off SLA with Solaria (who calls back, within how long) |

## Additional tests (all pass on v2)

| Scenario | Result |
|---|---|
| Wrong party (sister answers, ACC-1005) | `wrong_party_contact`; transcript has no amount or "pago"; data-quality task |
| Already paid (ACC-1006) | `paid_claimed` (not "paid") → finance reconciliation |
| No answer (ACC-1007, `call.failed`) | `no_contact`, review task, no redial |
| `call.result_validation_failed` | `needs_review` + QA task |
| CALL-E API down during verification | 503 (asks for redelivery); `/calls/{id}/sync` fallback works |
| CRM down when the campaign starts | 502, **zero calls placed** |
| CALL-E rejects the create | `submit_failed` recorded and reported |
| Do-not-call / 22:00 local time | Blocked before CALL-E |
| Campaign run twice | Second run is skipped; one call only (idempotency) |
| Webhook id mismatch / unknown call | 400 / ignored |
| Forged webhook body says "firm promise" | Ignored, because the outcome comes from the re-fetched API data |

## Improvement made after testing → retest
Commits `270ed09` (v1) → `24ac420` (v2):
1. **False success on CRM failure.** v1 logged the error and returned `200 synced`. CALL-E would not retry,
   and the outcome would have been lost. v2 adds an outbox and returns `202 crm_sync=pending_retry`. Success
   is only reported on the CRM's own confirmation. Retest: T3 passes.
2. **Ambiguous promise recorded as a promise.** v1 trusted `outcome=promise_to_pay`. v2 requires a specific,
   firm date within policy; anything else goes to a human. Retest: T2 passes. 3 failed → 17/17 pass.

## Remaining defects and limitations (honest list)
1. **No live CALL-E evidence in this log yet.** All call content is scripted. Untested: Spanish speech
   quality, real extraction accuracy, latency, voicemail/IVR behaviour, and whether `result_schema` is
   accepted on the live API (one community report says it was rejected). *Next: run 5-10 live calls to my
   own phone, playing each persona.*
2. **Outbox retry is manual** (`POST /outbox/retry`). There's no scheduler and no alerting.
3. **Webhook is unauthenticated** by CALL-E's design. We mitigate by re-fetching and by checking the call
   id is one we created. The URL should also carry an unguessable path segment in production.
4. **The calling window is a configuration assumption**, not a legal opinion. Mexican public holidays are
   not handled.
5. **The orchestrator stores `account_json` (PII) in plain SQLite.** It needs encryption and a retention
   policy before real data is used.
6. **One call per account per cycle.** There's no retry strategy for no-answer yet (on purpose, until the
   policy is agreed).
