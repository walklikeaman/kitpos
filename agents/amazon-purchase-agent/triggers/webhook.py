"""
FastAPI webhook trigger.

POST /purchase   — incoming purchase request (Slack, Telegram, or direct)
POST /confirm    — user confirmation to place the order
GET  /health     — liveness probe
"""
from __future__ import annotations
import hashlib
import hmac
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from agent.orchestrator import ProcurementOrchestrator
from agent.parser import parse_request
from config import config

app = FastAPI(title="Amazon Business Procurement Agent", version="0.1.0")

# In-memory session store (replace with Redis for multi-instance)
_sessions: dict[str, dict[str, Any]] = {}


class PurchasePayload(BaseModel):
    message: str
    session_id: str


class ConfirmPayload(BaseModel):
    session_id: str


def _verify_signature(body: bytes, signature: str) -> None:
    expected = hmac.new(config.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/purchase")
async def purchase(payload: PurchasePayload, request: Request):
    # 1. Parse
    req = parse_request(payload.message)

    if not req.ship_to:
        return {"status": "needs_input", "message": "Please provide a shipping address."}

    # 2. Build summary
    orchestrator = ProcurementOrchestrator(req)
    summary, issues = orchestrator.build_summary()
    formatted = orchestrator.format_summary(summary, issues)

    # 3. Store session
    _sessions[payload.session_id] = {
        "orchestrator": orchestrator,
        "summary": summary,
        "issues": issues,
        "auto_place": orchestrator.can_auto_place(summary, issues),
    }

    # 4. Auto-place if all conditions met
    if _sessions[payload.session_id]["auto_place"]:
        order = orchestrator.place_order(summary)
        del _sessions[payload.session_id]
        return {"status": "placed", "message": orchestrator.format_placed(order)}

    return {"status": "awaiting_confirmation", "message": formatted}


@app.post("/confirm")
async def confirm(payload: ConfirmPayload):
    session = _sessions.get(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or already used.")

    orchestrator: ProcurementOrchestrator = session["orchestrator"]
    summary = session["summary"]
    issues: list[str] = session["issues"]

    if issues:
        return {
            "status": "blocked",
            "message": "Cannot place order while there are unresolved issues:\n" + "\n".join(f"• {i}" for i in issues),
        }

    if not summary.cart:
        return {"status": "empty", "message": "No valid items in cart."}

    order = orchestrator.place_order(summary)
    del _sessions[payload.session_id]
    return {"status": "placed", "message": orchestrator.format_placed(order)}
