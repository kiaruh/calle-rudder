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
| CALL-E call execution | **Simulated by default; live available** | "Call my phone" in the UI (or `CALLE_MODE=live`) uses the official SDK and places real calls (allowlisted numbers only). In simulated mode the transcripts and extracted results are scripted fixtures in `app/simulator/scenarios/`. |
| Payment-link SMS | **Simulated** | Recorded in `/notifications`. Nothing is sent. |

## Quick start

New here? Read **[docs/00-start-here.md](docs/00-start-here.md)**. It covers running the project, the CALL-E dashboard, and
calling your own phone.

Needs Python 3.11 or newer (tested on 3.11 and 3.14). The scripts create a local `.venv`, so there's no global `pip install`.
Paste these commands one line at a time:

```bash
./setup.sh
./run.sh
```

`./run.sh` opens the **control center** at http://127.0.0.1:8000/ in your browser:

| Tab | What you can do |
|---|---|
| **Demo** | Reset, run the campaign, simulate each conversation, break the CRM and recover. Each button shows the matching `curl` command |
| **Call my phone** | Paste your CALL-E API key, enter your number, and get a **real** call. Scripts tell you what to say for each test |
| **Results** | Calls, CRM accounts, tasks, outbox. Click a call for the transcript, the extracted result and the CRM record |
| **Troubleshoot** | One-click health checks with fixes, plus common errors |
| **Learn AI Rudder** | Interview study guide: 7-min explainer video, AI Rudder + CALL-E, the role (Technical CSM + FDE), what to say, STAR, Q&A, flashcards. Also at `/rudder/` |
| **Learn** (`/learn`) | What CALL-E is, what this repo does, the system diagram, code map, terminal cheat sheet, all docs with diagrams |

Also: the mock CRM at http://127.0.0.1:8001/ (with outage buttons), and Swagger API docs at `/docs` on both ports.
`./demo.sh` runs the narrated terminal demo, starting the services if needed. Tests: `.venv/bin/python -m pytest -v`.
zsh doesn't treat `#` as a comment in interactive shells, so don't paste commands with trailing comments.

## Live CALL-E call (real phone, your own number)

The simplest way is the control center: **http://127.0.0.1:8000 → Call my phone**. Paste your key, enter your number, press
**Call me now**. Step-by-step guide: [docs/00-start-here.md](docs/00-start-here.md#3-call-your-own-phone-real-call-e).

Terminal alternative:
```bash
curl -X POST localhost:8000/api/live/key -H 'content-type: application/json' -d '{"api_key":"YOUR_KEY"}'
curl -X POST localhost:8000/api/live/call-me -H 'content-type: application/json' -d '{"phone":"+52XXXXXXXXXX","region":"MX","locale":"es-MX","timezone":"America/Mexico_City","consent":true}'
curl -X POST localhost:8000/calls/CALL_ID/sync
```
Repeat the last command until it returns `processed`. Live calls only go to numbers you entered (the allowlist).
To keep the key across restarts, set `CALLE_API_KEY` in `.env` (copy it from `.env.example`). Optional push results instead of
polling: `ngrok http 8000` and `PUBLIC_WEBHOOK_URL=https://<id>.ngrok.app/calle/webhook` in `.env`.

Mexico (`MX`, Spanish) is on CALL-E's supported list, but only through an **international** line, which CALL-E
describes as intended mainly for development and testing. A real pilot needs a local Mexican number or a SIP trunk
(see `docs/06-presentation.md`, rollout).

## Deploy online (Netlify + Render)

Netlify only hosts static pages, so the app is split in two. Both redeploy automatically on every push.

```
 Browser ──▶ Netlify (pages + video, CDN) ──proxy /api/*, /calls/*, /crm/*, /docs…──▶ Render (FastAPI backend)
             control center, /learn, /rudder/                                        orchestrator + mock CRM at /crm
```

| Piece | Config | What it runs |
|---|---|---|
| **Backend on Render** (free web service) | `render.yaml` | `app/combined.py`: the orchestrator with the mock CRM mounted at `/crm`, one process. They still talk over real HTTP (loopback), so outages and retries behave as they do locally |
| **Frontend on Netlify** | `netlify.toml` + `scripts/netlify_build.sh` | Copies `app/orchestrator/static/` to `dist/` and writes `_redirects`: static files first, everything else proxied to `BACKEND_URL` |

One-time setup:
1. **Render:** dashboard → **New → Blueprint** → pick this GitHub repo → **Apply**. Wait for the deploy, then copy the URL
   (e.g. `https://calle-rudder-api.onrender.com`). Under the service's **Environment**, note the generated `LIVE_PASSCODE`.
2. **Netlify:** **Add new site → Import an existing project** → GitHub → this repo. Build settings come from `netlify.toml`.
   Under **Site configuration → Environment variables**, add `BACKEND_URL` = the Render URL, then **Deploy**.
3. Open the Netlify URL. The control center, project guide (`/learn`), CRM (`/crm/`) and **Learn AI Rudder** (`/rudder/`) all work.

Things to know:
- **The free Render instance sleeps after ~15 min idle** and takes up to a minute to wake. The page shows a banner and retries
  by itself. Open the site a couple of minutes before presenting.
- **Shared demo state:** everyone who opens the site sees and changes the same CRM and calls. Press **Reset everything** before presenting.
  The databases are reset whenever Render restarts the instance.
- **Real calls are locked** on the public site: "Call my phone" asks for the `LIVE_PASSCODE` once per browser session, so visitors
  can't spend your CALL-E credits. The hosted backend has a public URL, so live calls get webhooks without ngrok.

## Repository map

```
app/crm/main.py                 Mock CRM service (SIMULATED system, real HTTP + SQLite)
app/orchestrator/agent_config.py  Voice agent: task instructions + result_schema + request builder
app/orchestrator/guards.py      Pre-call rules: phone present/valid, do-not-call, calling window
app/orchestrator/calle_gateway.py  CALL-E adapter: LiveCalleGateway (SDK) | SimulatedCalleGateway
app/orchestrator/outcomes.py    Business rules: verified call result -> CRM status + follow-up task
app/orchestrator/main.py        HTTP API: campaign, webhook, sync (poll), outbox retry
app/orchestrator/control.py     Control center API (/api/*): demo actions, live call, troubleshooting, docs
app/orchestrator/static/        Control center (index.html) and project guide (learn.html)
app/orchestrator/static/rudder/ Learn AI Rudder study guide (index.html), explainer video, video source (video/)
app/combined.py                 One-process backend for hosting (orchestrator + CRM at /crm), used by render.yaml
render.yaml, netlify.toml       Deployment: backend on Render, pages + proxy on Netlify (scripts/netlify_build.sh)
app/orchestrator/store.py       Orchestrator state: intents, idempotency keys, webhook receipts, outbox
app/simulator/scenarios/        Scripted calls for simulated mode (Spanish transcripts)
data/seed_accounts.json         8 fictional customers covering each path
tests/test_workflow.py          End-to-end tests (T1-T4 required + edge cases)
tests/test_control.py           Control center API + live path against a fake CALL-E (official SDK)
scripts/demo.py                 Live-demo script (6 acts)
docs/                           Scenario, agent design, integration, test log, decision log, presentation
docs/evidence/                  Captured test runs (v1 fail -> v2 pass) and demo output
```

## Documents for the interview

0. [Start here: run, rehearse, call your phone](docs/00-start-here.md)
1. [Customer scenario & scope](docs/01-scenario.md)
2. [Voice agent design: instructions vs workflow vs external logic](docs/02-agent-design.md)
3. [Integration: field mapping, success confirmation, failure handling](docs/03-integration.md)
4. [Test log](docs/04-test-log.md)
5. [Decision log](docs/05-decision-log.md)
6. [Presentation outline + rollout recommendation + Q&A prep](docs/06-presentation.md)
7. [Interview playbook: step by step for sections 1-6](docs/07-interview-playbook.md)
8. [Architecture](docs/ARCHITECTURE.md)
