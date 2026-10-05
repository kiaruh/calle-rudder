"""Pre-call guards: external logic that decides whether a call may be placed at all.

These run BEFORE anything is sent to CALL-E, so a missing phone number or a
do-not-call flag never turns into a real phone call.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

# Mexican numbers: +52 followed by 10 digits.
MX_E164 = re.compile(r"^\+52\d{10}$")


def _window() -> tuple[time, time]:
    # Conservative default inside the 07:00-22:00 debtor-local window commonly cited for
    # collections contact in Mexico. To be confirmed by the customer's compliance team.
    start, end = os.environ.get("CALL_WINDOW", "08:00-21:00").split("-")
    return time.fromisoformat(start), time.fromisoformat(end)


@dataclass
class GuardResult:
    allowed: bool
    code: str  # ok | missing_phone | invalid_phone | do_not_call | outside_calling_window | missing_amount
    detail: str


def check_account(account: dict[str, Any], now_utc: datetime) -> GuardResult:
    phone = (account.get("phone_e164") or "").strip()
    if not phone:
        return GuardResult(False, "missing_phone", "Account has no phone number on file.")
    if not MX_E164.match(phone):
        return GuardResult(False, "invalid_phone", "Phone is not a valid Mexican E.164 number (+52 + 10 digits).")
    if account.get("do_not_call"):
        return GuardResult(False, "do_not_call", "Customer opted out of calls.")
    if not account.get("amount_due_mxn") or not account.get("due_date"):
        return GuardResult(False, "missing_amount", "Amount or due date missing; agent would have nothing accurate to say.")
    tz = ZoneInfo(account.get("timezone") or "America/Mexico_City")
    local = now_utc.astimezone(tz)
    start, end = _window()
    if not (start <= local.time() < end):
        return GuardResult(
            False,
            "outside_calling_window",
            f"Local time {local:%H:%M} ({tz.key}) is outside {start:%H:%M}-{end:%H:%M}.",
        )
    return GuardResult(True, "ok", "")
