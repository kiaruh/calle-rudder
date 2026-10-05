"""Business rules: turn a verified CALL-E call snapshot into a CRM write.

This is deliberately outside the voice agent. CALL-E reports what happened on
the call; Solaria's policy decides what that means for the account. A completed
call is NOT proof of a promise, and an extracted value is not trusted blindly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .agent_config import OUTCOMES

# Policy: a promise counts only if it is on/after the call date and at most N days after the due date.
PTP_MAX_DAYS_AFTER_DUE = int(os.environ.get("PTP_MAX_DAYS_AFTER_DUE", "7"))


@dataclass
class Decision:
    outcome: str
    new_status: str
    task: dict[str, Any] | None
    review_reasons: list[str] = field(default_factory=list)
    send_payment_link: bool = False
    fields: dict[str, Any] = field(default_factory=dict)


def _task(type_: str, team: str, priority: str, description: str, due: str | None = None) -> dict[str, Any]:
    return {"type": type_, "team": team, "priority": priority, "due_date": due, "description": description}


def extract_result(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Structured result lives at the call level; fall back to the single recipient."""
    result = snapshot.get("structured_result")
    if result is None:
        recipients = snapshot.get("recipients") or []
        if recipients:
            result = recipients[0].get("structured_result")
    return result if isinstance(result, dict) else None


def decide(snapshot: dict[str, Any], account: dict[str, Any], call_date: str) -> Decision:
    status = snapshot.get("status")
    call_id = snapshot.get("id", "?")

    # 1. The call itself did not complete: never invent an outcome.
    if status in {"failed", "canceled"}:
        return Decision(
            outcome="no_contact",
            new_status="no_contact",
            task=_task("review_no_contact", "collections_ops", "normal",
                       f"CALL-E call {call_id} ended as '{status}'. Review contact strategy; no automatic redial."),
            review_reasons=[f"call_status_{status}"],
        )

    result = extract_result(snapshot)
    if result is None or result.get("outcome") not in OUTCOMES:
        return Decision(
            outcome="unknown",
            new_status="needs_review",
            task=_task("review_call", "qa", "normal",
                       f"No valid structured result for call {call_id}. Listen to the recording / read transcript."),
            review_reasons=["missing_or_invalid_structured_result"],
        )

    outcome = result["outcome"]
    fields = {
        "promise_date": result.get("promise_date") or None,
        "promise_amount_mxn": result.get("promise_amount_mxn"),
        "payment_channel": result.get("payment_channel"),
        "callback_window": result.get("callback_window") or None,
        "notes": result.get("customer_notes"),
        "evidence": result.get("outcome_evidence"),
    }
    reasons: list[str] = []

    # 2. Privacy guard: anything but a confirmed holder cannot produce a debt outcome.
    if outcome == "wrong_party" or result.get("right_party") == "wrong_person":
        return Decision(
            outcome="wrong_party", new_status="wrong_party_contact",
            task=_task("verify_contact_data", "data_quality", "normal",
                       "Someone other than the holder answered. Debt was not disclosed. Verify phone ownership."
                       + (f" Suggested callback: {fields['callback_window']}" if fields["callback_window"] else "")),
            fields=fields,
        )
    if outcome == "no_contact" or result.get("right_party") == "not_reached":
        return Decision(
            outcome="no_contact", new_status="no_contact",
            task=_task("review_no_contact", "collections_ops", "normal", "No answer / voicemail. No automatic redial."),
            fields=fields,
        )
    if result.get("right_party") != "confirmed":
        reasons.append("right_party_not_confirmed")

    if outcome == "promise_to_pay":
        promise = _parse_date(fields["promise_date"])
        due = _parse_date(account.get("due_date"))
        today = _parse_date(call_date)
        if promise is None:
            reasons.append("promise_without_specific_date")
        elif today and promise < today:
            reasons.append("promise_date_in_past")
        elif due and promise > due + timedelta(days=PTP_MAX_DAYS_AFTER_DUE):
            reasons.append(f"promise_date_beyond_policy_{PTP_MAX_DAYS_AFTER_DUE}d_after_due")
        if result.get("promise_certainty") != "firm":
            reasons.append(f"promise_certainty_{result.get('promise_certainty')}")
        if reasons:
            return Decision(
                outcome="promise_to_pay", new_status="needs_review",
                task=_task("confirm_promise", "collections_agents", "normal",
                           f"Customer indicated intent to pay but it is not a valid promise ({', '.join(reasons)}). "
                           "Agent to confirm a specific date.", due=call_date),
                review_reasons=reasons, fields=fields,
            )
        return Decision(
            outcome="promise_to_pay", new_status="promise_to_pay",
            task=_task("verify_payment", "collections_ops", "low",
                       f"Promise to pay {fields['promise_amount_mxn'] or account['amount_due_mxn']} MXN on "
                       f"{promise.isoformat()}. Verify payment received; if not, schedule follow-up.",
                       due=(promise + timedelta(days=1)).isoformat()),
            send_payment_link=True, fields=fields,
        )

    routing = {
        "already_paid": ("paid_claimed", _task("reconcile_payment", "finance", "normal",
                         "Customer states installment already paid. Reconcile before any further contact.")),
        "dispute": ("dispute", _task("dispute_ticket", "customer_support", "high",
                    "Customer disputes the amount/debt. Pause reminders until resolved.")),
        "hardship": ("hardship", _task("hardship_review", "collections_specialists", "high",
                     "Customer reports financial hardship. Review payment-plan eligibility.")),
        "callback_requested": ("callback_requested", _task("human_callback", "collections_agents", "normal",
                               f"Customer asked to be called back: {fields['callback_window'] or 'no time given'}.")),
        "human_requested": ("callback_requested", _task("human_callback", "collections_agents", "high",
                            f"Customer asked for a human advisor. Preferred time: {fields['callback_window'] or 'not given'}.")),
        "refused": ("refused", _task("supervisor_review", "collections_supervisors", "normal",
                    "Customer refused / asked not to be called. Review opt-out before any new contact.")),
    }
    if outcome in routing:
        new_status, task = routing[outcome]
        return Decision(outcome=outcome, new_status=new_status, task=task, review_reasons=reasons, fields=fields)

    return Decision(
        outcome="unknown", new_status="needs_review",
        task=_task("review_call", "qa", "normal", "Outcome unclear. Review transcript."),
        review_reasons=reasons + ["outcome_unknown"], fields=fields,
    )


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None
