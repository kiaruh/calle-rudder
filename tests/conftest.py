import pytest
from fastapi.testclient import TestClient

from app.crm.main import create_app as create_crm
from app.orchestrator.calle_gateway import SimulatedCalleGateway
from app.orchestrator.crm_client import CrmClient
from app.orchestrator.main import create_app as create_orch

# 12:00 in Mexico City on 2026-10-05: inside the calling window, 3 days before the due date.
NOON_CDMX = "2026-10-05T18:00:00+00:00"


class Env:
    def __init__(self, tmp_path):
        self.crm_app = create_crm(str(tmp_path / "crm.sqlite3"))
        self.crm = TestClient(self.crm_app)  # the orchestrator talks to the CRM over (in-process) HTTP
        self.gateway = SimulatedCalleGateway(auto_deliver=False)
        self.orch = TestClient(create_orch(self.gateway, CrmClient(self.crm), str(tmp_path / "orch.sqlite3")))

    def campaign(self, *ids, now=NOON_CDMX):
        r = self.orch.post("/campaigns/payment-reminders", json={"account_ids": list(ids), "now": now})
        return r

    def deliver(self, call_id, scenario=None):
        """Simulate CALL-E finishing the call and POSTing the terminal webhook."""
        event = self.gateway.complete(call_id, scenario)
        return self.orch.post("/calle/webhook", json=event, headers={"CALL-E-Event-Id": event["id"]}), event

    def account(self, account_id):
        return self.crm.get(f"/accounts/{account_id}").json()

    def tasks(self, account_id):
        return [t for t in self.crm.get("/tasks").json() if t["account_id"] == account_id]

    def call_row(self, account_id):
        return next(r for r in self.orch.get("/calls").json() if r["account_id"] == account_id)


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)
