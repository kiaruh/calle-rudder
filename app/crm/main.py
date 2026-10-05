"""Mock CRM for "Financiera Solaria" (fictional Mexican consumer lender).

SIMULATED SYSTEM. This stands in for the customer's real CRM / collections
platform (e.g. Salesforce, HubSpot, a core-banking collections module). It is a
real HTTP service with its own database, so the integration between the
orchestrator and the CRM genuinely executes over the network and can genuinely
fail. Only the CRM's identity is mocked.

Endpoints
  GET  /accounts                       list accounts
  GET  /accounts/{id}                  read one account (customer context for the call)
  POST /accounts/{id}/call-outcomes    idempotent write of one call outcome
                                       (interaction + status change + follow-up task)
  GET  /tasks                          follow-up queue for human teams
  GET  /interactions                   call history
  POST /admin/failure                  fault injection: {"mode": "none"|"error"|"timeout"}
  POST /admin/reset                    reseed from data/seed_accounts.json
  GET  /                               read-only HTML view for the demo
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
SEED_FILE = ROOT / "data" / "seed_accounts.json"

ACCOUNT_STATUSES = {
    "upcoming_due",
    "promise_to_pay",
    "paid_claimed",
    "dispute",
    "hardship",
    "callback_requested",
    "refused",
    "wrong_party_contact",
    "no_contact",
    "needs_review",
    "contact_data_missing",
}


class TaskIn(BaseModel):
    type: str
    team: str
    priority: Literal["low", "normal", "high"]
    due_date: str | None = None
    description: str


class CallOutcomeIn(BaseModel):
    call_id: str = Field(..., description="CALL-E call id (or a local id for blocked attempts). Idempotency key.")
    source: Literal["calle_live", "calle_simulated", "orchestrator"]
    outcome: str
    new_status: str
    promise_date: str | None = None
    promise_amount_mxn: float | None = None
    payment_channel: str | None = None
    callback_window: str | None = None
    notes: str | None = None
    evidence: str | None = None
    review_reasons: list[str] = []
    task: TaskIn | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_app(db_path: str | None = None) -> FastAPI:
    db_file = db_path or os.environ.get("CRM_DB", str(ROOT / "data" / "crm.sqlite3"))
    app = FastAPI(title="Mock CRM - Financiera Solaria (SIMULATED)", version="1.0")
    app.state.failure_mode = "none"

    def conn() -> sqlite3.Connection:
        c = sqlite3.connect(db_file)
        c.row_factory = sqlite3.Row
        return c

    def init(reset: bool = False) -> None:
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        with closing(conn()) as c, c:
            if reset:
                c.executescript("DROP TABLE IF EXISTS accounts; DROP TABLE IF EXISTS interactions; DROP TABLE IF EXISTS tasks;")
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                  account_id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS interactions (
                  call_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                  task_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, call_id TEXT NOT NULL,
                  type TEXT, team TEXT, priority TEXT, due_date TEXT, description TEXT, state TEXT, created_at TEXT);
                """
            )
            if c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
                for acc in json.loads(SEED_FILE.read_text(encoding="utf-8")):
                    c.execute(
                        "INSERT INTO accounts VALUES (?,?,?,?)",
                        (acc["account_id"], json.dumps(acc, ensure_ascii=False), acc["status"], _now()),
                    )

    init()

    @app.middleware("http")
    async def fault_injection(request: Request, call_next):
        # Fault injection only affects business endpoints, never /admin or the HTML view.
        if request.url.path.startswith(("/accounts", "/tasks", "/interactions")):
            mode = app.state.failure_mode
            if mode == "error":
                return JSONResponse({"error": "crm_unavailable", "detail": "Injected failure (SIMULATED outage)"}, status_code=503)
            if mode == "timeout":
                time.sleep(float(os.environ.get("CRM_TIMEOUT_SLEEP", "6")))
        return await call_next(request)

    def account_row(c: sqlite3.Connection, account_id: str) -> dict[str, Any]:
        row = c.execute("SELECT * FROM accounts WHERE account_id=?", (account_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"account {account_id} not found")
        data = json.loads(row["data"])
        data["status"] = row["status"]
        data["updated_at"] = row["updated_at"]
        return data

    @app.get("/accounts")
    def list_accounts() -> list[dict[str, Any]]:
        with closing(conn()) as c:
            ids = [r[0] for r in c.execute("SELECT account_id FROM accounts ORDER BY account_id")]
            return [account_row(c, i) for i in ids]

    @app.get("/accounts/{account_id}")
    def get_account(account_id: str) -> dict[str, Any]:
        with closing(conn()) as c:
            return account_row(c, account_id)

    @app.post("/accounts/{account_id}/call-outcomes")
    def write_outcome(account_id: str, body: CallOutcomeIn) -> JSONResponse:
        if body.new_status not in ACCOUNT_STATUSES:
            raise HTTPException(422, f"unknown status {body.new_status}")
        with closing(conn()) as c, c:
            account_row(c, account_id)  # 404 if missing
            existing = c.execute("SELECT payload FROM interactions WHERE call_id=?", (body.call_id,)).fetchone()
            if existing is not None:
                if json.loads(existing["payload"]) == body.model_dump():
                    return JSONResponse({"result": "duplicate", "call_id": body.call_id}, status_code=200)
                raise HTTPException(409, f"call {body.call_id} already recorded with different content")
            # One transaction: interaction + status + task. Either all land or none.
            c.execute(
                "INSERT INTO interactions VALUES (?,?,?,?)",
                (body.call_id, account_id, json.dumps(body.model_dump(), ensure_ascii=False), _now()),
            )
            c.execute("UPDATE accounts SET status=?, updated_at=? WHERE account_id=?", (body.new_status, _now(), account_id))
            task_id = None
            if body.task is not None:
                cur = c.execute(
                    "INSERT INTO tasks (account_id, call_id, type, team, priority, due_date, description, state, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (account_id, body.call_id, body.task.type, body.task.team, body.task.priority,
                     body.task.due_date, body.task.description, "open", _now()),
                )
                task_id = cur.lastrowid
        return JSONResponse(
            {"result": "created", "call_id": body.call_id, "account_status": body.new_status, "task_id": task_id},
            status_code=201,
        )

    @app.get("/tasks")
    def list_tasks() -> list[dict[str, Any]]:
        with closing(conn()) as c:
            return [dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY task_id")]

    @app.get("/interactions")
    def list_interactions() -> list[dict[str, Any]]:
        with closing(conn()) as c:
            return [
                {"call_id": r["call_id"], "account_id": r["account_id"], "created_at": r["created_at"], **json.loads(r["payload"])}
                for r in c.execute("SELECT * FROM interactions ORDER BY created_at")
            ]

    @app.post("/admin/failure")
    def set_failure(body: dict[str, str]) -> dict[str, str]:
        mode = body.get("mode", "none")
        if mode not in {"none", "error", "timeout"}:
            raise HTTPException(422, "mode must be none|error|timeout")
        app.state.failure_mode = mode
        return {"failure_mode": mode}

    @app.post("/admin/accounts/{account_id}/phone")
    def set_phone(account_id: str, body: dict[str, str]) -> dict[str, str]:
        """For live tests only: point a fictional account at a phone you own / are authorised to call."""
        with closing(conn()) as c, c:
            data = account_row(c, account_id)
            data["phone_e164"] = body.get("phone_e164", "")
            data.pop("updated_at", None)
            c.execute("UPDATE accounts SET data=?, updated_at=? WHERE account_id=?",
                      (json.dumps(data, ensure_ascii=False), _now(), account_id))
        return {"account_id": account_id, "phone_e164": data["phone_e164"]}

    @app.post("/admin/reset")
    def reset() -> dict[str, str]:
        init(reset=True)
        app.state.failure_mode = "none"
        return {"result": "reset"}

    @app.get("/", response_class=HTMLResponse)
    def view() -> str:
        with closing(conn()) as c:
            accs = [account_row(c, r[0]) for r in c.execute("SELECT account_id FROM accounts ORDER BY account_id")]
            tasks = [dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY task_id DESC")]
        rows = "".join(
            f"<tr><td>{a['account_id']}</td><td>{a['full_name']}</td><td>{a['city']}</td>"
            f"<td>${a['amount_due_mxn']:,.2f}</td><td>{a['due_date']}</td><td><b>{a['status']}</b></td></tr>"
            for a in accs
        )
        trows = "".join(
            f"<tr><td>{t['task_id']}</td><td>{t['account_id']}</td><td>{t['type']}</td><td>{t['team']}</td>"
            f"<td>{t['priority']}</td><td>{t['due_date'] or ''}</td><td>{t['description']}</td></tr>"
            for t in tasks
        )
        return _page(
            "Mock CRM - Financiera Solaria (SIMULATED)",
            f"<p>Failure mode: <b>{app.state.failure_mode}</b></p>"
            f"<h2>Accounts</h2><table><tr><th>Account</th><th>Name</th><th>City</th><th>Due</th><th>Due date</th><th>Status</th></tr>{rows}</table>"
            f"<h2>Follow-up tasks</h2><table><tr><th>#</th><th>Account</th><th>Type</th><th>Team</th><th>Priority</th><th>Due</th><th>Description</th></tr>{trows}</table>",
        )

    return app


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta http-equiv='refresh' content='3'>"
        f"<title>{title}</title><style>body{{font-family:system-ui;margin:24px;background:#fafafa}}"
        "table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid #ddd;padding:6px;font-size:14px;text-align:left}"
        f"th{{background:#eee}}</style></head><body><h1>{title}</h1>{body}</body></html>"
    )

