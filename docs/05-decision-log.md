# 5. Decision log

## D1. Business decisions live in code. The voice agent only reports.

| | |
|---|---|
| **Problem** | CALL-E is goal-driven, so it would be easy to tell it "if they promise, mark the account as PTP and send the link". But prompts are probabilistic. In collections, a wrong "promise" corrupts forecasts and can trigger wrong follow-up contact. |
| **Alternatives** | (a) Put the policy in the prompt and trust `outcome`. (b) Let the agent produce free text and parse it. (c) **Agent reports facts in a typed schema; deterministic rules in the orchestrator decide status and task.** |
| **Why (c)** | It can be tested and audited, and it can change without re-prompting. Compliance and finance can read `outcomes.py`. The same rules apply in live and simulated mode. |
| **Evidence** | v1 used (a) in practice: it trusted `outcome=promise_to_pay`. Test T2 caught "a fin de mes, si me pagan" being recorded as a promise. v2 adds the rule (specific date + `firm` + ≤ due+7d), and T2 passes. |
| **Trade-off accepted** | More fields in the schema (`promise_certainty`, `right_party`) mean more extraction that can go wrong. Some genuine promises will land in `needs_review` (false negatives), which costs agent time. |
| **Would change if** | Live data shows extraction is very accurate and `needs_review` volume overloads the agents. Then I would relax the rule, for example accepting tentative promises inside 3 days, rather than move logic into the prompt. |

## D2. Webhook as a wake-up signal + re-fetch + outbox, instead of trusting the webhook body

| | |
|---|---|
| **Problem** | CALL-E's webhooks are **unsigned** (SDK: "current CALL-E webhooks are unsigned"), possibly redelivered, and may not arrive at all (local demo, network). The CRM can be down when the result arrives. |
| **Alternatives** | (a) Trust the webhook body and write the CRM synchronously. (b) Polling only (`create_and_wait`). (c) **Webhook triggers processing; the call is re-read from the authenticated API; the CRM write goes through an idempotent outbox; polling `/sync` is the fallback.** |
| **Why (c)** | Anyone who knows the URL could POST a fake "firm promise", and (a) would believe it. (b) is simple but ties a worker to each multi-minute call and doesn't scale to campaigns. (c) follows CALL-E's own guidance (re-fetch is the trust boundary) and survives CRM outages and redelivery. |
| **Evidence** | T3: CRM 503 → no false success, outbox retry → exactly 1 task even after redelivery. Forged-body test: tampered values ignored. T3b: CALL-E API down → 503 + `/sync` fallback. v1 returned `200 synced` on CRM failure, and T3 caught it. |
| **Trade-off accepted** | One extra API read per call. More moving parts (outbox state). Retry is manual in this prototype. We return 202 (not 5xx) once the result is safely stored, so CALL-E's redelivery isn't our safety net; the outbox is. |
| **Would change if** | CALL-E signs webhooks (then re-fetch becomes optional), or the CRM offers a native idempotent upsert and queue, for example Salesforce Platform Events. |

## D3. Scope: one outbound reminder, no negotiation, no automatic redial, mock CRM

| | |
|---|---|
| **Problem** | The assignment rewards "small and well-tested". Collections conversations can expand without limit (plans, discounts, disputes, legal). |
| **Alternatives** | (a) Full collections agent that offers payment plans. (b) Reminder plus automatic retries for no-answer. (c) **A single reminder call. Anything that needs judgment becomes a routed human task. Mock CRM over real HTTP.** |
| **Why (c)** | Negotiation needs policy, legal approval and payment integration that don't exist yet. Auto-redial without an agreed contact policy is a compliance risk (contact-frequency limits). A mock CRM over HTTP lets me demo real failures (503, timeout) on demand, which a SaaS sandbox can't do reliably in a live demo. |
| **Evidence** | 8 fictional accounts exercise every outcome. Every non-happy path produces a specific task for a named team (see the routing table in `03-integration.md`). Blocked accounts never reach CALL-E (`gateway._calls == {}` in tests). |
| **Trade-off accepted** | Less automation value per call: hardship and dispute still need a human, and no-answers aren't retried. The CRM mapping must be redone for Solaria's real CRM. |
| **Would change if** | Pilot data shows that most human tasks are routine (e.g. "call me after 5" can be rescheduled by machine), or Solaria provides an approved payment-plan policy. Then I would add one capability at a time, each behind its own test. |

### Smaller decisions worth mentioning if asked
- **es-MX, *usted*, explicit "virtual assistant" disclosure.** It builds trust and is safer under evolving AI-disclosure expectations. The cost is possibly more early hang-ups; measure it (A5).
- **Idempotency key per account+cycle, saved before the network call.** A crash or retry can't double-call a customer.
- **Enum + `unknown` everywhere**, following CALL-E's own schema guidance.
- **Abort the whole campaign if the CRM can't be read.** It's better to call nobody than to call with stale amounts.
