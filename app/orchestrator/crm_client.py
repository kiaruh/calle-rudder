"""HTTP client for the (mock) CRM. Every failure becomes a CrmError - never a silent success."""

from __future__ import annotations

from typing import Any

import httpx


class CrmError(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class CrmClient:
    def __init__(self, http: httpx.Client):
        self.http = http

    @classmethod
    def from_url(cls, base_url: str, timeout: float = 3.0) -> "CrmClient":
        return cls(httpx.Client(base_url=base_url, timeout=timeout))

    def _send(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            resp = self.http.request(method, path, **kw)
        except httpx.TimeoutException as exc:
            raise CrmError(f"CRM timeout on {method} {path}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise CrmError(f"CRM unreachable on {method} {path}: {exc}", retryable=True) from exc
        if resp.status_code >= 500:
            raise CrmError(f"CRM {resp.status_code} on {method} {path}: {resp.text[:200]}", retryable=True)
        if resp.status_code >= 400:
            raise CrmError(f"CRM rejected {method} {path} ({resp.status_code}): {resp.text[:200]}", retryable=False)
        return resp

    def get_account(self, account_id: str) -> dict[str, Any]:
        return self._send("GET", f"/accounts/{account_id}").json()

    def list_accounts(self) -> list[dict[str, Any]]:
        return self._send("GET", "/accounts").json()

    def write_outcome(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Returns the CRM's confirmation. 201 created or 200 duplicate both mean 'recorded'."""
        body = self._send("POST", f"/accounts/{account_id}/call-outcomes", json=payload).json()
        if body.get("result") not in {"created", "duplicate"}:
            raise CrmError(f"Unexpected CRM confirmation: {body}", retryable=False)
        return body
