"""Orchestrator's own durable state (SQLite).

The orchestrator owns: business intent saved *before* calling CALL-E, the
returned call id, webhook receipts (dedup), and an outbox of CRM writes that
have not been confirmed yet. CALL-E owns call execution state; the CRM owns
account state.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._c()) as c, c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS call_requests (
                  idempotency_key TEXT PRIMARY KEY, account_id TEXT, cycle TEXT, call_date TEXT,
                  account_json TEXT, request_json TEXT, call_id TEXT UNIQUE, state TEXT, detail TEXT,
                  outcome TEXT, crm_status TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS webhook_events (
                  event_id TEXT PRIMARY KEY, call_id TEXT, type TEXT, body TEXT, received_at TEXT);
                CREATE TABLE IF NOT EXISTS outbox (
                  call_id TEXT PRIMARY KEY, account_id TEXT, payload TEXT, state TEXT, attempts INTEGER,
                  last_error TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS notifications (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT, call_id TEXT, channel TEXT,
                  body TEXT, simulated INTEGER, created_at TEXT);
                """
            )

    def reset(self) -> None:
        with closing(self._c()) as c, c:
            c.executescript("DELETE FROM call_requests; DELETE FROM webhook_events; DELETE FROM outbox; DELETE FROM notifications;")

    def last_webhook(self) -> dict[str, Any] | None:
        with closing(self._c()) as c:
            r = c.execute("SELECT event_id, call_id, type, received_at FROM webhook_events ORDER BY received_at DESC LIMIT 1").fetchone()
            return dict(r) if r else None

    def _c(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    # --- call requests ------------------------------------------------------------
    def get_request(self, key: str) -> dict[str, Any] | None:
        with closing(self._c()) as c:
            r = c.execute("SELECT * FROM call_requests WHERE idempotency_key=?", (key,)).fetchone()
            return dict(r) if r else None

    def get_by_call_id(self, call_id: str) -> dict[str, Any] | None:
        with closing(self._c()) as c:
            r = c.execute("SELECT * FROM call_requests WHERE call_id=?", (call_id,)).fetchone()
            return dict(r) if r else None

    def save_intent(self, key: str, account: dict[str, Any], cycle: str, call_date: str,
                    request: dict[str, Any] | None, state: str, detail: str = "") -> None:
        with closing(self._c()) as c, c:
            c.execute(
                "INSERT INTO call_requests (idempotency_key, account_id, cycle, call_date, account_json, request_json,"
                " state, detail, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(idempotency_key) DO UPDATE SET request_json=excluded.request_json, state=excluded.state,"
                " detail=excluded.detail, updated_at=excluded.updated_at",
                (key, account["account_id"], cycle, call_date, json.dumps(account, ensure_ascii=False),
                 json.dumps(request, ensure_ascii=False) if request else None, state, detail, now(), now()),
            )

    def update_request(self, key: str, **fields: Any) -> None:
        fields["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        with closing(self._c()) as c, c:
            c.execute(f"UPDATE call_requests SET {cols} WHERE idempotency_key=?", (*fields.values(), key))

    def list_requests(self) -> list[dict[str, Any]]:
        with closing(self._c()) as c:
            return [dict(r) for r in c.execute(
                "SELECT idempotency_key, account_id, cycle, call_id, state, detail, outcome, crm_status, updated_at"
                " FROM call_requests ORDER BY account_id")]

    # --- webhook receipts ---------------------------------------------------------
    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with closing(self._c()) as c:
            r = c.execute("SELECT * FROM webhook_events WHERE event_id=?", (event_id,)).fetchone()
            return dict(r) if r else None

    def save_event(self, event_id: str, call_id: str, type_: str, body: str) -> None:
        with closing(self._c()) as c, c:
            c.execute("INSERT OR IGNORE INTO webhook_events VALUES (?,?,?,?,?)", (event_id, call_id, type_, body, now()))

    # --- outbox -------------------------------------------------------------------
    def outbox_put(self, call_id: str, account_id: str, payload: dict[str, Any]) -> None:
        with closing(self._c()) as c, c:
            c.execute(
                "INSERT INTO outbox VALUES (?,?,?,?,?,?,?) ON CONFLICT(call_id) DO NOTHING",
                (call_id, account_id, json.dumps(payload, ensure_ascii=False), "pending", 0, None, now()),
            )

    def outbox_mark(self, call_id: str, state: str, error: str | None = None) -> None:
        with closing(self._c()) as c, c:
            c.execute(
                "UPDATE outbox SET state=?, attempts=attempts+1, last_error=?, updated_at=? WHERE call_id=?",
                (state, error, now(), call_id),
            )

    def outbox_pending(self) -> list[dict[str, Any]]:
        with closing(self._c()) as c:
            return [dict(r) | {"payload": json.loads(r["payload"])}
                    for r in c.execute("SELECT * FROM outbox WHERE state='pending' ORDER BY updated_at")]

    def outbox_all(self) -> list[dict[str, Any]]:
        with closing(self._c()) as c:
            return [dict(r) for r in c.execute("SELECT call_id, account_id, state, attempts, last_error, updated_at FROM outbox")]

    # --- simulated outbound notifications -----------------------------------------
    def add_notification(self, account_id: str, call_id: str, channel: str, body: str) -> None:
        with closing(self._c()) as c, c:
            c.execute("INSERT INTO notifications (account_id, call_id, channel, body, simulated, created_at)"
                      " VALUES (?,?,?,?,1,?)", (account_id, call_id, channel, body, now()))

    def notifications(self) -> list[dict[str, Any]]:
        with closing(self._c()) as c:
            return [dict(r) for r in c.execute("SELECT * FROM notifications ORDER BY id")]
