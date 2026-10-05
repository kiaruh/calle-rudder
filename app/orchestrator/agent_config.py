"""Voice agent configuration: what CALL-E is told, and what it must hand back.

Three layers control the agent's behaviour (see docs/02-agent-design.md):

1. INSTRUCTIONS (this file, `build_task`): the natural-language goal CALL-E
   receives. Covers purpose, tone, right-party check, the allowed scope, and
   the exceptions to handle in-conversation (wrong person, unclear answer,
   request for a human, dispute, hardship).
2. WORKFLOW CONFIGURATION (this file, `RESULT_SCHEMA` + `build_request`):
   locale/region, the structured result contract, metadata for correlation,
   webhook URL, idempotency key.
3. EXTERNAL LOGIC (guards.py, outcomes.py): who may be called and when, and
   what the business does with the result. The voice agent never decides a
   CRM status or creates a task by itself.
"""

from __future__ import annotations

from typing import Any

COMPANY = "Financiera Solaria"
AGENT_NAME = "Sofía"
SCHEMA_VERSION = "2026-10-v2"

# Outcome vocabulary shared by the schema, the business rules and the CRM.
OUTCOMES = [
    "promise_to_pay",
    "already_paid",
    "dispute",
    "hardship",
    "callback_requested",
    "human_requested",
    "refused",
    "wrong_party",
    "no_contact",
    "unknown",
]

RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["right_party", "outcome", "promise_certainty", "needs_human", "outcome_evidence"],
    "properties": {
        "right_party": {
            "type": "string",
            "enum": ["confirmed", "wrong_person", "not_reached", "unknown"],
            "description": (
                "confirmed only if the person explicitly confirmed they are the account holder by name. "
                "wrong_person if someone else answered or said the holder is not available. "
                "not_reached if nobody answered or it was voicemail. unknown otherwise."
            ),
        },
        "outcome": {
            "type": "string",
            "enum": OUTCOMES,
            "description": (
                "promise_to_pay: the holder stated a day they will pay. "
                "already_paid: the holder says the installment is already paid. "
                "dispute: the holder disagrees with the amount or says the debt is not theirs. "
                "hardship: the holder says they cannot pay because of financial difficulty. "
                "callback_requested: the holder asked to be called at another time. "
                "human_requested: the holder asked to speak to a person/advisor. "
                "refused: the holder refused to talk or to pay and gave no other request. "
                "wrong_party: the account holder was not reached because someone else answered. "
                "no_contact: nobody answered or voicemail. "
                "unknown: the call does not clearly support any other value."
            ),
        },
        "promise_date": {
            "type": "string",
            "description": (
                "Only for promise_to_pay: the payment date as YYYY-MM-DD, resolved against the call date given "
                "in the task. Empty string if no specific calendar day was stated (e.g. 'when I get paid', "
                "'end of the month, if I can'). Never guess a date."
            ),
        },
        "promise_certainty": {
            "type": "string",
            "enum": ["firm", "tentative", "not_applicable", "unknown"],
            "description": (
                "firm: an unconditional commitment to a specific day. tentative: conditional or hedged "
                "('si puedo', 'creo que', 'a ver si'). not_applicable when outcome is not promise_to_pay."
            ),
        },
        "promise_amount_mxn": {
            "type": "number",
            "description": "Amount in MXN the holder said they will pay. Omit if not stated.",
        },
        "payment_channel": {
            "type": "string",
            "enum": ["spei_transfer", "oxxo", "bank_branch", "solaria_app", "unknown"],
            "description": "How the holder said they will pay. unknown if not stated.",
        },
        "callback_window": {
            "type": "string",
            "description": "For callback_requested or human_requested: the day/time the holder prefers, in their words. Empty if none.",
        },
        "needs_human": {
            "type": "string",
            "enum": ["yes", "no", "unknown"],
            "description": "yes if the holder asked for a person, disputed the debt, described hardship, or was upset.",
        },
        "customer_notes": {
            "type": "string",
            "description": "One or two English sentences a collections agent needs to know. No card numbers or full IDs.",
        },
        "outcome_evidence": {
            "type": "string",
            "description": "The holder's own words (Spanish, verbatim) that support the outcome, or why the outcome is unknown.",
        },
    },
}


def mask_phone(phone: str) -> str:
    return phone[:5] + "*" * max(len(phone) - 7, 0) + phone[-2:] if phone else ""


def language_line(locale: str) -> str:
    lang = (locale or "es-MX").split("-")[0]
    return {
        "es": {"es-MX": "Speak natural, polite Mexican Spanish (usted).",
               "es-AR": "Speak natural, polite Argentine Spanish (usted)."}.get(locale, "Speak natural, polite Spanish (usted)."),
        "zh": "Speak natural, polite Mandarin Chinese.",
        "en": "Speak natural, polite English.",
        "pt": "Speak natural, polite Brazilian Portuguese.",
    }.get(lang, f"Speak in the language for locale {locale}.")


def build_task(account: dict[str, Any], call_date: str) -> str:
    """Natural-language instructions sent to CALL-E for one account."""
    amount = f"${account['amount_due_mxn']:,.2f} MXN"
    return f"""You are {AGENT_NAME}, a virtual assistant (AI) calling on behalf of {COMPANY}, a consumer lender in Mexico.
{language_line(account.get("locale") or "es-MX")} Keep the call under 3 minutes. Today is {call_date}.

PURPOSE: a courtesy reminder that installment #{account['installment_number']} of the customer's "{account['product']}"
for {amount} is due on {account['due_date']}, and to learn if and when they plan to pay.

STEP 1 - Identify yourself and say you are a virtual assistant of {COMPANY}. Ask to speak with {account['full_name']}.
STEP 2 - Right-party check: ask the person to confirm they are {account['full_name']}.
  - If it is someone else, or the holder is not available: do NOT mention the loan, the amount or any debt.
    Only say {COMPANY} will call back, ask for a good time to reach the holder, thank them and end the call.
STEP 3 - With the confirmed holder: remind them of the amount and due date. Payment reference: {account['payment_reference']}.
  Payment options: SPEI transfer, OXXO, bank branch, or the Solaria app. Say a payment link will be sent by SMS.
STEP 4 - Ask on which day they plan to pay. If the answer is vague ("luego", "a fin de mes", "cuando me paguen"),
  ask ONCE for a specific day. If it stays vague, accept it politely; do not pressure.
STEP 5 - Confirm back what you understood (date, amount, channel) and close politely.

EXCEPTIONS:
- If they ask for a person/advisor, say an advisor will call them back, ask for the best time, and end the call.
- If they say they already paid, thank them and say the payment will be verified. Do not argue.
- If they dispute the amount or the debt, do not argue; say an advisor will review it and contact them.
- If they mention financial difficulty, be empathetic and say an advisor can review options. Do not offer anything yourself.
- If they ask you to stop calling or refuse to talk, apologise, confirm you will note it, and end the call.

NEVER: threaten, mention legal action, credit bureaus or penalties not stated here; offer discounts, plans or
extensions; take card numbers, passwords or payment over the phone; discuss the debt with anyone but the holder;
claim to be a human.
"""


def build_request(account: dict[str, Any], *, call_date: str, cycle: str, webhook_url: str | None) -> dict[str, Any]:
    """Full CALL-E POST /v1/calls body (minus the Idempotency-Key header)."""
    body: dict[str, Any] = {
        "task": build_task(account, call_date),
        "recipients": [{"phones": [account["phone_e164"]], "region": account.get("region") or "MX",
                        "locale": account.get("locale") or "es-MX"}],
        "result_schema": RESULT_SCHEMA,
        "metadata": {
            "account_id": account["account_id"],
            "campaign": "payment-reminder",
            "cycle": cycle,
            "schema_version": SCHEMA_VERSION,
        },
    }
    if webhook_url:
        body["webhook_url"] = webhook_url
    return body


def idempotency_key(account_id: str, cycle: str) -> str:
    """One reminder call per account per billing cycle, even across retries/restarts."""
    return f"solaria-reminder-{cycle}-{account_id}"
