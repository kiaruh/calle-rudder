# 6. Presentation (15 min) + Q&A prep

Five slides at most. Most of the time goes to the live demo.

---

## Slide 1: Customer objective and scope (2 min)
- **Financiera Solaria** (fictional MX lender): remind customers 3 days before an installment is due and
  turn each call into **one actionable CRM outcome**.
- Success = a confirmed holder gives a firm date → `promise_to_pay` + a payment-verification task + an SMS link.
- Boundaries: AI-disclosed reminder in es-MX. No negotiation, no payments on the call, no debt talk with
  third parties, no auto-redial.
- *Say:* "I chose payment reminders because it's AI Rudder's core use case, and because it has the
  clearest 'actionable outcome': a dated promise you can check."

## Slide 2: Workflow and integration (3 min)
- Show `docs/ARCHITECTURE.md` (or the architecture page).
- Three layers: **Instructions** (task prompt) · **Workflow config** (schema, locale, metadata,
  idempotency) · **External logic** (guards before, rules after).
- Real vs simulated table (README). "The integration with the CRM really executes over HTTP. CALL-E runs
  live with my key, or simulated with the identical contract."

## Live demo (5 min): `./run.sh` + `python3 scripts/demo.py`
| Act | Show | Point to make |
|---|---|---|
| 1 | CRM account JSON | Input: fictional customer context |
| 2 | Campaign results | 6 submitted, **2 blocked before CALL-E** (no phone, DNC). Masked phones |
| 3 | Calls table + CRM tasks (dashboard :8001) | Every call ends in an honest status, and each task goes to a named team |
| 4 | structured_result → CRM interaction | Field mapping, evidence quote kept |
| 5 | **CRM goes down** mid-call | 202 `pending_retry`, `crm_sync_failed`, outbox pending. **No false success** |
| 6 | CRM back, outbox retry | CRM 201 confirmation; exactly one task |
| (opt.) | Live CALL-E call to my phone | Real Spanish call, if time and the network allow |

Backup if the demo fails: `docs/evidence/demo_run_simulated.txt` and `pytest -v`.

## Slide 3: Test findings and decisions (3 min)
- 4 required tests + 13 edge cases. **v1 failed 2 of the 4 required tests (T2 and T3)**:
  - T2: "a fin de mes, si me pagan" was recorded as a promise → fixed with the promise rule.
  - T3: CRM outage → v1 said "200 synced" → fixed with the outbox + honest status.
  - Retest 17/17. Git history shows both versions.
- Decisions: D1 rules in code, not prompt · D2 webhook = signal, API = truth, outbox · D3 narrow scope.
- Remaining defects: no live extraction evidence yet, manual retry, unsigned webhook, PII at rest.

## Slide 4: Rollout recommendation (2 min)
**Ready for a pilot? A controlled one, after a short pre-pilot. Not yet for production volume.**

Ready now: workflow logic, failure handling, CRM contract, guardrails.
Not ready: live Spanish extraction accuracy is unproven; the MX line is **international** (CALL-E: "intended
primarily for development and testing"), which likely hurts pickup rates and trust; compliance sign-off.

**Phases**
1. *Pre-pilot (1-2 weeks):* 30-50 internal calls to employee phones with personas. Measure extraction
   accuracy against human labels. Legal review of the script.
2. *Pilot (4 weeks):* 500-1,000 low-risk accounts (upcoming due, not delinquent). A/B against SMS-only.
   100% human QA on `needs_review`, plus 10% QA sampling on the rest.
3. *Expand* only if the success criteria below are met.

**Needs Engineering / Product (CALL-E side)**
- Local Mexican caller ID or SIP trunk; webhook signing; confirm `result_schema` support and the webhook
  retry policy; recording/transcript retention options.

**Needs the customer (Solaria)**
- Compliance: calling window, AI-disclosure wording, privacy notice, contact-frequency limits.
- Real CRM fields/API, human callback SLA, payment-link provider, opt-out handling.

## Slide 5: Metrics and evidence to expand
| Metric | Why | Pilot target (to agree) |
|---|---|---|
| Right-party contact rate | Line quality and caller-ID trust | ≥ 35% |
| Early hang-up rate (< 10 s) | AI disclosure and persona acceptance | ≤ 25% |
| Outcome distribution, especially `unknown`/`needs_review` | Extraction and design quality | `unknown` ≤ 5% |
| **Extraction accuracy vs human label** | Can the data be trusted? | ≥ 95% on `outcome`, ≥ 90% on `promise_date` |
| **Promise-kept rate** (paid by the promised date) | The real business value | Better than the SMS-only control |
| On-time payment rate vs control | Incremental impact | +X pp (statistically significant) |
| Human-task volume and SLA met | Does it save or create work? | Callback within 24 h ≥ 90% |
| CRM sync failures / outbox age | Integration health | 0 lost; p99 sync < 5 min |
| Complaints / opt-outs | Customer harm | No increase vs baseline |
| Cost per right-party contact vs a human agent | ROI | Lower than the agent baseline |

**Evidence to justify expanding:** promise-kept and on-time-payment rates beat the control over 2 billing
cycles, accuracy is above target, there are no compliance incidents, and the human-task load stays within
team capacity.

---

## Q&A prep (likely questions)
- **"Why not let CALL-E decide the outcome?"** It does extract the outcome. We decide what it *means*, see D1.
- **"What if the webhook never arrives?"** Use `/calls/{id}/sync` polling. A real deployment adds a sweeper
  that polls calls stuck in `submitted` for more than 15 min.
- **"How do you know the CRM write succeeded?"** Only the CRM's 201/200 confirmation counts. Before that,
  the write sits in the outbox as `pending`.
- **"Why 202 and not 500 on CRM failure?"** The result is already durable in our outbox, so redelivery adds
  nothing. 503 is used when we *can't* verify (CALL-E API down), because then we want redelivery.
- **"Why would a promise go to review if the customer clearly committed?"** Policy (date > due + 7 days)
  or the date wasn't specific. Volume is monitored, and the threshold is configurable
  (`PTP_MAX_DAYS_AFTER_DUE`).
- **"Mexico specifics?"** Several time zones (window per customer), *usted*, OXXO/SPEI channels,
  CONDUSEF collection rules, LFPDPPP privacy, and the international vs local caller-ID issue.
- **"What did you find when exploring CALL-E?"** It's goal-driven (task + schema), not a flow builder. It
  has MCP and SDK/API paths, a statuses and events model, unsigned webhooks, idempotency keys, and a region
  table with MX on an international line. I chose the Developer API path because a backend integration
  needs webhooks, metadata and idempotency, which the MCP `run_call` doesn't expose (no `webhook_url`).
- **"What would you do with one more week?"** Live calls and an accuracy study, an automatic retry
  worker with alerting, a real CRM sandbox (HubSpot), and a QA review screen showing transcript + evidence.
