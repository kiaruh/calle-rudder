# 0. Start here

## The three pieces

| Piece | What it is | Where |
|---|---|---|
| **CALL-E** (by AI Rudder) | A cloud product that makes phone calls for you. You give it a goal in plain language and a phone number. It plans the call, talks to the person and returns a summary, transcript and structured result. | heycall-e.com (website and dashboard), api.heycall-e.com (developer API) |
| **This repo: orchestrator** | The glue a CSM builds for a customer. It decides who to call, tells CALL-E what to say and what to extract, checks the result, and writes it into the customer's CRM. | http://127.0.0.1:8000 (control center UI) |
| **Mock CRM** | A stand-in for the customer's CRM (Salesforce, HubSpot…), with fictional Mexican customers. | http://127.0.0.1:8001 |

Without a CALL-E key, CALL-E is **simulated**: the conversations are scripted, and everything else runs for real. With your API key, the
"Call my phone" button places a **real** call to your phone.

## 1. Run it (on your Mac)

Paste these commands one line at a time:

```
./setup.sh
./run.sh
```

`./setup.sh` is needed only once. `./run.sh` starts both services and opens **http://127.0.0.1:8000/** in your browser.
Leave that terminal open; Ctrl+C stops everything.

## 2. Rehearse the demo (no CALL-E account needed)

Tip: the **Presenter guide** at the top of the control center walks you through every step: what to click, what you
should see, what to say, and what it means in plain words. Pressing Next highlights the button to click, a green ✓
appears automatically when a step's result is really on screen, arrow keys (← →) move between steps, and a small
follow-along bar keeps the current step visible while you scroll. "Start over" resets it for another rehearsal.
There's also a glossary.

On the control center's **Demo** tab:

1. **Reset everything.**
2. **Run campaign (8 accounts).** 6 calls go out and 2 are blocked before dialing (one has no phone, one is do-not-call).
3. Open the **Results** tab. Click a call to see the Spanish transcript, what CALL-E extracted, what the orchestrator decided and what the CRM stored.
4. **Run outage scenario.** The CRM goes down while a call is in flight, and the call shows `crm_sync_failed`. Nothing reports false success.
5. **Restore CRM + retry outbox.** The CRM confirms the write, and exactly one task is created.
6. Use the **Simulate** buttons to play any single conversation: firm promise, vague answer, asks for a human, wrong person, already paid, no answer.

Every button has a "Terminal equivalent" showing the `curl` command that does the same thing.

## 3. Call your own phone (real CALL-E)

### In the CALL-E website/dashboard
1. Go to **https://www.heycall-e.com/** and create an account. New accounts get 100 free credits (about US$1).
2. Optional, but good preparation for the interview: try the product as an end user. In the CALL-E web app, type a goal like
   *"Call +52… and ask if they can attend a meeting on Friday"* with **your** number. You'll see CALL-E plan the call, ask
   for missing details, confirm, call you, and show the summary and transcript. That is the "customer experience" the assignment
   asks you to explore.
3. Open **https://dashboard.heycall-e.com/account/api-keys** and create an API key. Copy it.
4. Usage and credits are under **https://dashboard.heycall-e.com/account/billing**.

> These steps come from CALL-E's public README. Menu names in the dashboard may differ slightly.

### In the control center (http://127.0.0.1:8000 → "Call my phone")
1. **Step 1:** paste the API key and press **Save & verify key**. It should say "API key accepted".
   The key stays in the server's memory only. To keep it across restarts, copy `.env.example` to `.env` and set `CALLE_API_KEY=`.
2. **Step 2:** choose your country, then type your number in E.164 format (Mexico: `+52` followed by 10 digits, e.g. `+525512345678`).
   Choose the call language (Spanish (Mexico) for the real scenario). Your time zone is filled in automatically.
3. Pick a script from **What to say on the call**. For example, for the normal test:
   - Agent: *"¿Hablo con María Fernanda López García?"* → You: **"Sí, soy yo."**
   - Agent reminds you of the $2,450 MXN payment → You: **"El viernes nueve hago la transferencia por SPEI."**
4. **Step 3:** tick the consent box and press **Call me now**. Answer your phone and act out the script.
5. The page checks CALL-E every 5 seconds. When the call ends, it shows the outcome and the CRM status, with a link to the transcript.
   The CRM row for ACC-1001 updates too.
6. Press **Back to simulated mode** when you're done.

Things to know:
- **Countries.** The dropdown lists CALL-E's supported countries (US, CA, MX, SG, ES, BR, GB, DE, IN and others).
  **Argentina (+54) and China (+86)** are also listed, marked "not on CALL-E's list". The app sends the call, but CALL-E will
  most likely reject it, and the rejection message is shown. CALL-E's guidance for unlisted destinations is a SIP integration.
  Formats: Argentina mobile `+54 9` + area code + number (e.g. `+5491123456789`); China mobile `+86` + 11 digits;
  Singapore `+65` + 8 digits (supported, English).
- **Mexico uses an international line**, so the caller ID may look foreign. Mention this in the interview: it's a pilot blocker.
- **Calling hours.** The guard blocks calls outside 08:00–21:00 in your time zone. That's on purpose; it's a compliance rule.
- **No webhook needed.** Without a public URL, the app polls CALL-E. Optionally, `ngrok http 8000` plus
  `PUBLIC_WEBHOOK_URL=https://<id>.ngrok.app/calle/webhook` in `.env` makes CALL-E push results.
- **Each live call is a real finding.** Write down what CALL-E extracted compared with what you said. That's live evidence for the test log
  (`docs/04-test-log.md`), which currently only has simulated runs.

## 4. If something goes wrong
Open the **Troubleshoot** tab and press **Run checks**. It checks the services, the CRM, your CALL-E key and network,
the webhook, the outbox and stuck calls, and says how to fix each failure. Below that is a table of common errors.

## 5. Understand the project
Open **http://127.0.0.1:8000/learn**. It covers what CALL-E is, what the repo does, the system diagram, who decides what,
a code map, a terminal cheat sheet, and all the documents in `docs/` rendered with their diagrams.

## 6. Interview-day checklist
The full step-by-step for every assignment section is in [07-interview-playbook.md](07-interview-playbook.md).

- [ ] `./run.sh` is running before the call starts. Browser tabs open: control center, CRM :8001, `/learn`.
- [ ] Press **Reset everything** right before presenting.
- [ ] Optional live moment: API key saved, phone entered, one script chosen. Do it once beforehand to check it works.
- [ ] Backup if anything fails: `docs/evidence/demo_run_simulated.txt` and `.venv/bin/python -m pytest -v`.
- [ ] Presentation outline and Q&A prep: `docs/06-presentation.md`.
