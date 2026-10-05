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
E164 = re.compile(r"^\+[1-9]\d{7,14}$")

# CALL-E supported destinations (from the CALL-E integrations README): region -> calling code.
CALLING_CODES = {
    "US": "+1", "CA": "+1", "AU": "+61", "BD": "+880", "BR": "+55", "DE": "+49", "ES": "+34", "FI": "+358",
    "GB": "+44", "ID": "+62", "IN": "+91", "JP": "+81", "MX": "+52", "MY": "+60", "NL": "+31", "PH": "+63",
    "PK": "+92", "PL": "+48", "SG": "+65", "TH": "+66", "TR": "+90", "VN": "+84",
}

# Requested for testing but NOT on CALL-E's published list. Calls are attempted so CALL-E's real
# answer (most likely a rejection, or a request to use a SIP integration) is visible, not hidden.
UNLISTED_CALLING_CODES = {"AR": "+54", "CN": "+86"}

COUNTRY_NAMES = {
    "US": "United States", "CA": "Canada", "AU": "Australia", "BD": "Bangladesh", "BR": "Brazil", "DE": "Germany",
    "ES": "Spain", "FI": "Finland", "GB": "United Kingdom", "ID": "Indonesia", "IN": "India", "JP": "Japan",
    "MX": "Mexico", "MY": "Malaysia", "NL": "Netherlands", "PH": "Philippines", "PK": "Pakistan", "PL": "Poland",
    "SG": "Singapore", "TH": "Thailand", "TR": "Turkey", "VN": "Viet Nam", "AR": "Argentina", "CN": "China",
}


def country_options() -> list[dict[str, object]]:
    """Dropdown data: supported countries first (by name), then the unlisted ones."""
    def row(code: str, cc: str, supported: bool) -> dict[str, object]:
        return {"code": code, "name": COUNTRY_NAMES.get(code, code), "calling_code": cc, "supported": supported}
    listed = sorted((row(c, cc, True) for c, cc in CALLING_CODES.items()), key=lambda r: r["name"])
    unlisted = sorted((row(c, cc, False) for c, cc in UNLISTED_CALLING_CODES.items()), key=lambda r: r["name"])
    return listed + unlisted


def validate_phone(phone: str, region: str) -> str | None:
    """Return an error message, or None if the number is acceptable for that region."""
    codes = {**CALLING_CODES, **UNLISTED_CALLING_CODES}
    if region not in codes:
        return f"Region {region} is not in CALL-E's supported list."
    if region == "MX":
        return None if MX_E164.match(phone) else "Not a valid Mexican E.164 number (+52 followed by 10 digits)."
    if not E164.match(phone):
        return "Not a valid E.164 number (+, country code, number; no spaces)."
    if not phone.startswith(codes[region]):
        return f"Number does not start with {codes[region]}, the calling code for {region}."
    return None


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
    error = validate_phone(phone, account.get("region") or "MX")
    if error:
        return GuardResult(False, "invalid_phone", error)
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
