# 1. Customer scenario and scope

## Customer
**Financiera Solaria** (fictional) is a consumer lender in Mexico offering personal loans and motorcycle credit
paid in fixed installments. Customers are spread across several Mexican time zones (CDMX, Monterrey,
Tijuana, Cancún, Chihuahua).

## Problem
- Many customers who pay late are not unwilling to pay. They forget, or they get paid after the due date.
- Agents spend most of their reminder time on calls that end in "yes, I'll pay Friday" or no answer at all.
- When an agent does get a commitment, it ends up in free-text notes, so nobody can reliably check
  "did they pay on the day they promised?"

## Objective (chosen scenario: **payment reminders**)
Call customers **3 days before** an installment is due. Remind them of the amount and due date, and capture
**one actionable outcome** per customer as structured data in the CRM, with a follow-up task routed to the
right team.

## Workflow boundaries

| In scope (the agent does it) | Out of scope (a human or another system does it) |
|---|---|
| Identify as Solaria's **virtual assistant** | Negotiating amounts, discounts, extensions, payment plans |
| Confirm the account holder before saying anything about the debt | Taking payments or card data on the call |
| State amount, due date, reference, payment channels | Legal or collections escalation, credit bureau talk |
| Ask for a payment date; clarify once if vague | Deciding whether a promise is acceptable (policy rule in the backend) |
| Handle: wrong person, request for a human, dispute, hardship, already paid, refusal | Reconciling a claimed payment (finance) |
| Produce a structured result | Redialing (never automatic) |

**Who is called:** accounts with an upcoming installment, a valid Mexican phone, no do-not-call flag, and
only between 08:00 and 21:00 in the **customer's** local time. That window is a conservative assumption to
validate with Solaria's compliance team against CONDUSEF's collection rules.

## What a successful interaction looks like
1. The holder is confirmed by name, and the debt is never mentioned to anyone else.
2. The holder gives a **specific, unconditional** date on or before due date + 7 days. For example:
   *"El viernes nueve hago la transferencia por SPEI."*
3. The CRM account changes to `promise_to_pay` and has a `verify_payment` task due the day after the promise.
   A payment link SMS is queued. The CRM confirmed the write (`201 created`).

Anything else is still a **successful run** if it ends in the correct, honest state. Examples: "needs
review" for a vague answer, "callback requested" with a high-priority human task, "no contact" with no
automatic redial. What must **never** happen is a false outcome (a promise that wasn't made) or a false
success (we say "saved" but the CRM doesn't have it).

## Fictional data set (`data/seed_accounts.json`)

| Account | City / TZ | Exercises |
|---|---|---|
| ACC-1001 María Fernanda | CDMX | Normal path: firm promise to pay |
| ACC-1002 José Luis | Monterrey | Ambiguous answer: "a fin de mes, si me pagan" |
| ACC-1003 Ana Sofía | Guadalajara | Customer exception: asks for a human |
| ACC-1004 Carlos Alberto | Tijuana | Missing data: no phone, so no call is made |
| ACC-1005 Guadalupe | Cancún | Wrong party (sister answers): no disclosure |
| ACC-1006 Ricardo | Puebla | Already paid, so the case goes to finance |
| ACC-1007 Daniela | Querétaro | No answer (`call.failed`) |
| ACC-1008 Fernando | Chihuahua | Do-not-call, so the account is blocked before CALL-E |

## Assumptions and dependencies to validate
| # | Assumption | How to validate |
|---|---|---|
| A1 | CALL-E can call Mexico in Spanish | Confirmed in CALL-E's published region list (`MX`, English/Spanish). It is an **international** line ("intended primarily for development and testing"). |
| A2 | `result_schema` with enums is extracted reliably in Spanish | **Unverified**: needs live calls. The docs show the feature, but one community skill reports the API rejecting `result_schema`. Test it with a live call before the pilot. |
| A3 | Webhooks are delivered at least once and are unsigned | The SDK marks the signature helpers deprecated ("current CALL-E webhooks are unsigned"). Retry policy not confirmed, so we don't depend on it. Polling is the fallback. |
| A4 | Calling window and disclosure rules | To confirm with Solaria legal/compliance (CONDUSEF collection rules, AI disclosure, LFPDPPP privacy notice). |
| A5 | Customer accepts a "virtual assistant" persona | Measure the hang-up rate in the first seconds during the pilot. |
