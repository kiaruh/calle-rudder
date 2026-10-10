# 7. Interview playbook: step by step, sections 1 to 6

This follows the assignment's numbering. Every step has three parts:
- **Do:** the click or command.
- **See:** what should appear.
- **Say:** what it means, in words you can use in the interview.

Do it once on your own, then do it again out loud as a rehearsal.

**Easiest way to follow this:** the control center (http://127.0.0.1:8000) has a **Presenter guide** panel at the top with the same
steps. Pressing **Next** (or the → key) switches to the right tab and briefly highlights the exact button to click.
Steps with a visible result have a live check in the "You should see" box: it turns **green with a ✓** by itself once the
system really shows that result, so you know you did the step correctly; a verified step's dot turns into a green ✓.
When you scroll away, a small **follow-along bar** at the bottom right keeps the current step and the Next button in view.
**Start over** resets the walkthrough for another rehearsal. Each demo card also has a "Say this" note. Turn the guide and
the notes off with the buttons in the header once you know the flow.

---

## Step 0: Get the project running (once, ~5 min)

| # | Do | See |
|---|---|---|
| 0.1 | Open Terminal and `cd` into the project folder (e.g. `cd ~/Desktop/calle-rudder-claude-affectionate-euler-cvrdsm`) | |
| 0.2 | Get the latest code (`git pull`, or download the branch again) | |
| 0.3 | `./setup.sh` | Ends with "39 passed" and "Ready. Next: ./run.sh" |
| 0.4 | `./run.sh` | The browser opens **http://127.0.0.1:8000/** (the control center). Leave this terminal open; Ctrl+C stops everything. |
| 0.5 | In the browser, also open **http://127.0.0.1:8001/** (mock CRM) and **http://127.0.0.1:8000/learn** (Learn page) | Three tabs, ready to use |

Paste terminal commands one line at a time. zsh breaks on pasted `# comments`.

---

## Section 1: Objective (know what they're grading)

**Do:** read this table once. Every part of the demo maps to one of their four questions.

| They want to see how you… | Where you show it |
|---|---|
| Turn a customer need into a working solution | Section 3 (scenario) + 4A (agent design) |
| Connect systems and troubleshoot | 4B (integration) + the Troubleshoot tab |
| Test and interpret results | 4C (tests, before/after improvement, live call) |
| Explain decisions, trade-offs, limits | Section 5 (decision log) + the rollout slide |

**Say (your one-line thesis):** *"I built a small payment-reminder workflow for a Mexican lender on CALL-E, and focused on making
it honest: it never records an outcome that didn't happen, and never reports a CRM update that didn't land."*

---

## Section 2: Project links and preparation (~1-2 hours)

### 2.1 Explore the CALL-E product as a customer
| # | Do | Look for / note down |
|---|---|---|
| 1 | Open **https://www.heycall-e.com/** | How they describe it: "your AI agent for getting phone work done". It's goal-driven, not a script builder. |
| 2 | Sign up (100 free credits ≈ US$1) | |
| 3 | In the CALL-E app, ask it to call **your own phone** with a simple goal (e.g. "Call +52… and ask if they can meet Friday at 10") | Watch the flow: it **plans**, **asks for missing details**, asks you to **confirm**, **dials**, then shows a **summary + transcript + result**. |
| 4 | Answer and talk to it. Try interrupting it, or asking "who are you?" | How natural it is, whether it discloses it's an AI, the latency, and the caller ID (Mexico uses an international number). |
| 5 | Write 3 observations | You'll use them in the intro: "I tried it as a user first, and noticed X, Y, Z." |

### 2.2 Read the integrations repo: https://github.com/CALLE-AI/call-e-integrations
| # | Do | Takeaway (say this if asked "what did you learn?") |
|---|---|---|
| 1 | README → "Capabilities" | Structured results, scheduled and batch calls, IVR navigation, voicemail handling, governance controls |
| 2 | README → "MCP" | 3 tools: `plan_call` → `run_call` → `get_call_run`. Made for AI agents, and **no webhook**, so it relies on polling |
| 3 | README → "SDK" / "API" | `POST /v1/calls` with `task`, `recipients` (`region`, `locale`), `result_schema`, `metadata`, `webhook_url`, and an `Idempotency-Key` header. **This is what I used.** |
| 4 | README → "Supported Regions" | **Mexico = MX, Spanish, International line** ("intended primarily for development and testing") |
| 5 | Search the repo for "unsigned" | Webhooks are **not signed**, so you must re-read the call from the API before trusting it |

### 2.3 Skim the examples repo: https://github.com/CALLE-AI/awesome-phone-call-agents
| # | Do | Takeaway |
|---|---|---|
| 1 | Open `skills/lead-qualification-call` and `skills/invoice-payment-chaser` | The community pattern: one call, a structured JSON result, and humans make the money decisions. My design follows it. |
| 2 | Open `apps/python/webhook-result-receiver/README.md` | Their guidance: "an unverified webhook is a wake-up signal, not business authority". I implemented exactly that. |

### 2.4 Confirm capabilities vs assumptions
**Do:** open `docs/01-scenario.md` → "Assumptions and dependencies to validate". **Say:** *"Before designing, I separated what I
confirmed from what I'm assuming."*
- **Confirmed:** MX + Spanish are supported, there's a result schema, webhooks exist and are unsigned, idempotency keys are supported.
- **Unverified:** how accurately it extracts results in Spanish, and whether `result_schema` is accepted live. Your live call in 4C tests both.
- **Customer-side:** calling hours and disclosure rules (Mexican collections rules), to be confirmed with their compliance team.

---

## Section 3: Customer scenario (~2 min in the interview)

| # | Do | See | Say |
|---|---|---|---|
| 1 | Read `docs/01-scenario.md` once | | |
| 2 | Show **http://127.0.0.1:8001/** (mock CRM) | 8 fictional customers across Mexican cities and time zones | *"Financiera Solaria is a fictional consumer lender. Most late payers just forgot or get paid later, and agents waste time on calls that end in 'I'll pay Friday'."* |
| 3 | Point at the "Status" column | All `upcoming_due` | *"Objective: call 3 days before the due date, remind them, and capture **one actionable outcome** per customer in the CRM."* |
| 4 | | | *"Boundaries: the agent reminds and listens. It never negotiates, takes payments, threatens, or talks about the debt with anyone but the account holder. Anything needing judgment becomes a task for a human."* |
| 5 | | | *"Success = a confirmed holder gives a specific date, so the CRM shows 'promise to pay' plus a task to check the payment. But it also counts as success when we record an honest 'needs review' instead of a fake promise."* |

---

## Section 4A: Configure the voice agent

| # | Do | See | Say |
|---|---|---|---|
| 1 | Control center → **Demo** → **Reset everything** → **Run campaign (8 accounts)** | "6 calls submitted. Blocked before CALL-E: ACC-1004 (missing_phone), ACC-1008 (do_not_call)" | *"Two customers were never called. That's external logic deciding before anything reaches CALL-E."* |
| 2 | Click **Open Results** → click the row **ACC-1001** | A dialog with the conversation, what CALL-E extracted, the decision, and the CRM record | |
| 3 | In the dialog, open **"Request sent to CALL-E (task prompt + schema)"** | The `task` text and the `result_schema` JSON | *"This is the whole agent configuration. CALL-E is goal-driven, so I don't draw a dialogue tree. I write instructions and the shape of the answer I need."* |
| 4 | Scroll the `task`: STEP 1–5, EXCEPTIONS, NEVER | | **Instructions:** *"Purpose and AI disclosure, a right-party check before mentioning the debt, clarify a vague date once, handle human/dispute/hardship/already-paid/refusal, and never threaten or take card data."* |
| 5 | Scroll the `result_schema` and `recipients` (`region: MX`, `locale: es-MX`) | Enum fields, each with `unknown` | **Workflow config:** *"The outcome is an enum with an 'unknown' option so the model can't force a guess. The date must be ISO. I also ask how certain the promise was (firm or tentative). Plus locale, metadata, and an idempotency key so we never call twice."* |
| 6 | Open `docs/02-agent-design.md` → the "Where each behaviour is controlled" table | | **External logic:** *"Who may be called and when, and what an answer means for the account, live in code I can test, not in the prompt."* |
| 7 | Back to **Demo** → under "Simulate one conversation", click **Simulate** on **Asks for a human** | A few seconds later, Results shows ACC-1001 → `callback_requested` | *"Exception handling: the customer asks for a person, so the agent stops, asks for a good time, and a high-priority callback task goes to the collections team."* |
| 8 | Optional: also **Wrong person answers** | `wrong_party_contact` | *"The sister answered, and the debt was never mentioned. That's a privacy rule."* |

---

## Section 4B: Implement one working integration

**What's real:** the orchestrator (:8000) and the CRM (:8001) are two separate services talking over HTTP.
CALL-E is simulated unless you use "Call my phone". Always state this clearly.

| # | Do | See | Say |
|---|---|---|---|
| 1 | **Learn page** → "System diagram" | Numbered flow 1–6 | *"1 read the account, 2 create the call, 3 the conversation, 4 webhook, 5 re-read the call from the API, 6 write to the CRM through an outbox."* |
| 2 | **Input:** tab :8001, or in Terminal: `curl localhost:8001/accounts/ACC-1001` | Name, phone, amount, due date, time zone | *"This is the customer context the agent uses."* |
| 3 | **Output:** Results → click ACC-1001 → compare "What CALL-E extracted" with "What the CRM stored" | `promise_date: 2026-10-09`, `payment_channel: spei_transfer`, a task `verify_payment` due 10-10 | **Field mapping:** *"promise_date goes to the interaction, and the follow-up task is due the next day. The customer's words are kept as evidence. Full table in docs/03."* |
| 4 | Open `docs/03-integration.md` → "Field mapping" + "Outcome → CRM routing" | | *"Every outcome routes to a named team with a priority."* |
| 5 | **How success is confirmed:** in the dialog's "What the CRM stored", or the Activity panel → "promise_to_pay -> CRM promise_to_pay" | | *"I only call it success when the CRM itself answers '201 created'. A completed call is not a business result."* |
| 6 | **Missing data:** Results → ACC-1004 is `blocked:missing_phone`; CRM tasks show `fix_contact_data` | | *"No phone means no call, and the data team gets a task."* |
| 7 | **Integration failure:** Demo → **Run outage scenario** → wait ~5 s → Results | ACC-1001: `crm_sync_failed`; Outbox: 1 `pending`; header chip "CRM: outage:error" | *"The call finished, but the CRM was down. The system says so: 'pending retry', not success. The result is safe in the outbox."* |
| 8 | Demo → **Restore CRM + retry outbox** | "Outbox retry: 1/1 delivered, and the CRM confirmed each one". The call becomes `synced` | *"When the CRM is back, it's delivered exactly once. If CALL-E sends the webhook again, it's a duplicate and no second task is created."* |
| 9 | Optional, to show it from the terminal: `curl localhost:8000/api/troubleshoot` | JSON health checks | *"Everything the UI does is a plain API call, so it's scriptable."* |

---

## Section 4C: Test and improve the solution

### Run the four required tests
| Test | Do (UI) | Expected (what you see) |
|---|---|---|
| **T1 Normal** | Demo → Simulate **Firm promise to pay** | `promise_to_pay`, `verify_payment` task, SMS link queued |
| **T2 Ambiguous** | Simulate **Vague answer** | Outcome says promise, but the CRM shows **`needs_review`** + a `confirm_promise` task for a human, and no SMS |
| **T3 Integration failure** | **Run outage scenario** → **Restore CRM + retry outbox** | `crm_sync_failed` → `synced`, with one task |
| **T4 Customer exception** | Simulate **Asks for a human** | `callback_requested`, a high-priority `human_callback` task |

**Automated proof:** in a second Terminal, `.venv/bin/python -m pytest -v`. You'll see 39 passed; the names `test_t1_…` to `test_t4_…` are the 4 required tests.

### Show the improvement and retest (this is required)
| # | Do | See | Say |
|---|---|---|---|
| 1 | `git log --oneline` | `270ed09` v1 … `24ac420` Fix… | |
| 2 | `cat docs/evidence/v1_test_run.txt` | v1 failed T2 and T3 | *"My first version failed two required tests. A vague 'end of the month, if I get paid' became a firm promise. And when the CRM was down, it still said 'synced'. That would silently lose the result."* |
| 3 | `git show 24ac420 --stat` | The fix touches `outcomes.py` and `main.py` | *"The fix: a promise needs a specific, firm date within policy, and CRM writes go through an outbox. Success is only reported when the CRM confirms."* |
| 4 | `cat docs/evidence/v2_test_run.txt` | All pass | *"Retest: everything passes."* |

### Add one live test with your phone (strongly recommended)
| # | Do | See |
|---|---|---|
| 1 | CALL-E dashboard → **dashboard.heycall-e.com/account/api-keys** → create a key | |
| 2 | Control center → **Call my phone** → paste the key → **Save & verify key** | "API key accepted" |
| 3 | Country **Mexico (+52)** (or yours), your number, language **Spanish (Mexico)** | The format hint under the fields |
| 4 | Pick the script **Firm promise to pay**, tick the consent box → **Call me now** | Your phone rings |
| 5 | Agent: "¿Hablo con María Fernanda López García?" → **"Sí, soy yo."** Agent reminds you → **"El viernes nueve hago la transferencia por SPEI."** | |
| 6 | Wait; the page checks every 5 s | "Finished. Outcome promise_to_pay → CRM promise_to_pay". Click **Open transcript** |
| 7 | Repeat with **Vague answer** (T2) and **Asks for a human** (T4) | |
| 8 | Press **Back to simulated mode** | |
| 9 | Add a row per call to `docs/04-test-log.md` (template below) | |

```
| L1 Live (real CALL-E) | Firm promise via my phone | promise_to_pay, date 2026-10-09 | <what CALL-E extracted> | call_id <id>, transcript screenshot | <e.g. date resolved correctly / wrong; next action> |
```
If CALL-E rejects the request (e.g. a 422 about `result_schema`), **that's a finding**. Write it down and say it in the
interview: *"Live testing showed X, so the next action is Y."*

### Remaining defects (say them before they ask)
*"No live accuracy study yet. Outbox retry is manual. The webhook is unsigned by CALL-E's design, so I mitigate by
re-reading. Customer data is stored unencrypted in this prototype. The Mexican line is international."* (List: `docs/04-test-log.md`, bottom.)

---

## Section 5: Explain your decisions

**Do:** read `docs/05-decision-log.md`. For each decision, practise the 6 answers out loud in about 45 seconds.

| Decision | One-line version | Evidence to point at |
|---|---|---|
| **D1** Business rules in code, not in the prompt | *"The agent reports facts, and my code decides what they mean, because prompts are probabilistic and money decisions shouldn't be."* | T2 failed in v1 and passes in v2 |
| **D2** Webhook as a signal + re-read + outbox | *"Webhooks are unsigned and the CRM can fail, so I re-read the call from the API and only count CRM-confirmed writes."* | Outage scenario; forged-webhook test |
| **D3** Narrow scope: one reminder, no negotiation, no auto-redial | *"Small and well-tested beats big and fragile. Anything that needs judgment becomes a routed human task."* | Every non-happy path ends in a named task |

Each decision has: problem → alternatives → why → evidence → trade-off → what would change my mind. They're all in the doc.

---

## Section 6: Presentation and live demo (15 min + 15–20 min Q&A)

### The day before
- [ ] Rehearse the whole run-of-show below twice, timing it.
- [ ] Do one live call to your phone, so you know it works and have a transcript to show if live fails.
- [ ] Build ≤5 slides from `docs/06-presentation.md` (slide 1 scenario, 2 architecture, 3 tests and decisions, 4 rollout, 5 metrics).

### 30 minutes before
- [ ] `./run.sh` running. Browser tabs: control center, CRM :8001, `/learn`, slides.
- [ ] Control center → **Reset everything**.
- [ ] Optional live: API key saved, phone filled in, phone on loud, Do Not Disturb off.
- [ ] Second terminal open in the project folder (for `git log` / `pytest`).

### Run-of-show (what to click, minute by minute)
| Min | Section | Click | Say |
|---|---|---|---|
| 0–2 | Objective & scope | Slide 1, then the CRM :8001 tab | Section 3 lines |
| 2–5 | Workflow & integration | `/learn` → System diagram; then a call's "Request sent to CALL-E" | Three layers (4A) + the 6 steps (4B) |
| 5–10 | **Live demo** | Demo → **Run campaign** → Results → click ACC-1001 → Simulate **Vague answer** → **Run outage scenario** → **Restore CRM + retry outbox**. Optional: **Call me now** | "6 called, 2 blocked" → "here's the mapping" → "vague isn't a promise" → "failure detected, not hidden" → "recovered exactly once" |
| 10–13 | Tests & decisions | Second terminal: `cat docs/evidence/v1_test_run.txt`, then slide 3 | v1 failed T2/T3 → fix → retest; D1–D3 one-liners |
| 13–15 | Rollout | Slides 4–5 | The four closing answers below |

### The four closing answers (from `docs/06-presentation.md`)
1. **Ready for a pilot?** *"Yes for a small, controlled pilot after a 1–2 week pre-pilot of internal test calls. Not for full volume: Spanish extraction accuracy isn't proven live yet, and Mexico is on an international line."*
2. **What needs others?** *"Engineering/Product (CALL-E side): a local Mexican number or SIP, webhook signing, confirming the schema support. The customer: compliance sign-off, their real CRM API, and a callback SLA."*
3. **Metrics:** *"Right-party contact rate, early hang-ups, % unknown/needs-review, extraction accuracy against human labels, **promise-kept rate**, on-time payment vs an SMS-only control, human task load, CRM sync failures, complaints."*
4. **Evidence to expand:** *"Promise-kept and on-time rates beat the control over two billing cycles, accuracy is above target, there are no compliance incidents, and the human workload fits the team."*

### If something breaks during the demo
| Problem | Do |
|---|---|
| Page won't load | Terminal: Ctrl+C, then `./run.sh` again |
| Something looks odd | **Troubleshoot** tab → **Run checks** (and say: *"This is how I'd troubleshoot for a customer"*) |
| Live call fails | *"Live calls depend on the international line, which is exactly the pilot risk I flagged."* Then switch to the simulated flow. |
| Everything fails | `cat docs/evidence/demo_run_simulated.txt` and `.venv/bin/python -m pytest -v` |

### Q&A prep
The likely questions and answers are at the bottom of `docs/06-presentation.md` (why not let CALL-E decide, what if the webhook never
arrives, why 202 and not 500, Mexico specifics, what you'd do with one more week).
