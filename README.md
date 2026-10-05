# Solaria Payment Reminders: CALL-E voice agent + CRM integration

AI Rudder Technical CSM practical assignment.

**Scenario:** *Financiera Solaria* (a fictional consumer lender in Mexico) wants an AI voice agent to call
customers before an installment is due, remind them in Mexican Spanish, and record the outcome (promise to
pay, already paid, dispute, hardship, asks for a human, etc.) in its CRM. That record has to be something a
collections team can act on. All customer data is fictional.

```
 Mock CRM  ──GET account──▶  Orchestrator  ──POST /v1/calls──▶  CALL-E  ──☎──▶  Customer
 (SIMULATED)                (this repo)                        (LIVE or        (Spanish, es-MX)
     ▲                          │  ▲                            SIMULATED)
     │                          │  └──── webhook: call.completed / call.failed ──┘
     └── POST call-outcome ◀────┘        then GET /v1/calls/{id} (verify) → business rules
         (status + follow-up task)
```

## What is real and what is simulated

| Component | Status | Notes |
|---|---|---|
| Orchestrator (campaign, guards, webhook receiver, rules, outbox) | **Real** | `app/orchestrator/`, runs as an HTTP service on :8000 |
| CRM integration (HTTP read of customer context, HTTP write of outcomes and tasks) | **Real HTTP, mocked system** | `app/crm/` is a separate service on :8001 with its own DB. It stands in for Salesforce/HubSpot/core banking. Its outages are injected but real (actual 503s and timeouts). |
| CALL-E request (task prompt, `result_schema`, region/locale, metadata, idempotency key) | **Real contract** | Built against the `calle-ai` 0.7.0 SDK and the public API docs |
| CALL-E call execution | **Simulated by default; live available** | `CALLE_MODE=live` uses the official SDK and places real calls (allowlisted numbers only). In simulated mode the transcripts and extracted results are scripted fixtures in `app/simulator/scenarios/`. |
| Payment-link SMS | **Simulated** | Recorded in `/notifications`. Nothing is sent. |

## Quick start (simulated, 2 minutes)

Needs Python 3.11 or newer (tested on 3.11 and 3.14). The scripts create a local `.venv`, so there's no global
`pip install`. That matters on macOS/Homebrew, where `pip` is missing and global installs are blocked.

```bash
./setup.sh
./demo.sh
```

- `./setup.sh` runs once. It creates `.venv`, installs dependencies and runs the 17 tests.
- `./demo.sh` starts the CRM (:8001) and orchestrator (:8000) if they aren't running, then plays the narrated
  demo. Press Enter between acts.
- To keep the services and dashboards running on their own, run `./run.sh` in one terminal (Ctrl+C stops it)
  and `./demo.sh` in a second terminal.

Paste the commands one line at a time. zsh doesn't treat `#` as a comment in interactive shells, so text after
a `#` gets run as part of the command.

To run the tests again: `.venv/bin/python -m pytest -v`. If `python3` is older than 3.11, point setup at a
newer one: `PYTHON=python3.13 ./setup.sh`.

Dashboards (refresh every 3 s): orchestrator http://127.0.0.1:8000/ · CRM http://127.0.0.1:8001/ ·
Swagger UI at `/docs` on both.

## Live CALL-E call (real phone, your own number)

1. Create a key at https://dashboard.heycall-e.com/account/api-keys (new accounts get 100 free credits).
2. `cp .env.example .env` and set `CALLE_MODE=live`, `CALLE_API_KEY=...`, and `CALLE_ALLOWED_PHONES=+52XXXXXXXXXX`
   (a phone you own). Any other number is refused before the API is called.
3. Optional: expose :8000 with `ngrok http 8000` and set `PUBLIC_WEBHOOK_URL=https://<id>.ngrok.app/calle/webhook`.
4. `./setup.sh` (once), `./run.sh`, then point a fictional account at your phone and start the call:
   ```bash
   curl -X POST localhost:8001/admin/accounts/ACC-1001/phone -H 'content-type: application/json' -d '{"phone_e164":"+52XXXXXXXXXX"}'
   curl -X POST localhost:8000/campaigns/payment-reminders -H 'content-type: application/json' -d '{"account_ids":["ACC-1001"]}'
   ```
5. Answer the call and play the customer. With no webhook URL, poll until the call is processed:
   `curl -X POST localhost:8000/calls/<call_id>/sync`
6. Check the result: `curl localhost:8000/calls/<call_id>/snapshot` (CALL-E's view) and http://127.0.0.1:8001/ (CRM).

Mexico (`MX`, Spanish) is on CALL-E's supported list, but only through an **international** line, which CALL-E
describes as intended mainly for development and testing. A real pilot needs a local Mexican number or a SIP trunk
(see `docs/06-presentation.md`, rollout).

## Repository map

```
app/crm/main.py                 Mock CRM service (SIMULATED system, real HTTP + SQLite)
app/orchestrator/agent_config.py  Voice agent: task instructions + result_schema + request builder
app/orchestrator/guards.py      Pre-call rules: phone present/valid, do-not-call, calling window
app/orchestrator/calle_gateway.py  CALL-E adapter: LiveCalleGateway (SDK) | SimulatedCalleGateway
app/orchestrator/outcomes.py    Business rules: verified call result -> CRM status + follow-up task
app/orchestrator/main.py        HTTP API: campaign, webhook, sync (poll), outbox retry, dashboard
app/orchestrator/store.py       Orchestrator state: intents, idempotency keys, webhook receipts, outbox
app/simulator/scenarios/        Scripted calls for simulated mode (Spanish transcripts)
data/seed_accounts.json         8 fictional customers covering each path
tests/test_workflow.py          End-to-end tests (T1-T4 required + edge cases)
scripts/demo.py                 Live-demo script (6 acts)
docs/                           Scenario, agent design, integration, test log, decision log, presentation
docs/evidence/                  Captured test runs (v1 fail -> v2 pass) and demo output
```

## Documents for the interview

1. [Customer scenario & scope](docs/01-scenario.md)
2. [Voice agent design: instructions vs workflow vs external logic](docs/02-agent-design.md)
3. [Integration: field mapping, success confirmation, failure handling](docs/03-integration.md)
4. [Test log](docs/04-test-log.md)
5. [Decision log](docs/05-decision-log.md)
6. [Presentation outline + rollout recommendation + Q&A prep](docs/06-presentation.md)
7. [Architecture](docs/ARCHITECTURE.md)
