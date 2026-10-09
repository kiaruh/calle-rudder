"""Single-process deployment (Render, or any host that gives you one web port).

Locally, ./run.sh starts two services: the orchestrator (:8000) and the mock CRM (:8001).
A free hosting instance exposes one port, so here the CRM is mounted at /crm inside the same
server. The orchestrator still talks to it over real HTTP (loopback to its own port), so the
integration, outages and retries behave exactly as they do locally.

    uvicorn app.combined:create_app --factory --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import os

from fastapi import FastAPI


def create_app() -> FastAPI:
    port = os.environ.get("PORT", "8000")
    os.environ.setdefault("CRM_BASE_URL", f"http://127.0.0.1:{port}/crm")
    os.environ.setdefault("SIM_WEBHOOK_URL", f"http://127.0.0.1:{port}/calle/webhook")
    # Render publishes the service's public URL; with it, live CALL-E calls can push results (no ngrok needed).
    if os.environ.get("RENDER_EXTERNAL_URL"):
        os.environ.setdefault("PUBLIC_WEBHOOK_URL", os.environ["RENDER_EXTERNAL_URL"].rstrip("/") + "/calle/webhook")

    from app.crm.main import create_app as create_crm
    from app.orchestrator.main import create_app as create_orch

    app = create_orch()
    app.mount("/crm", create_crm())
    return app
