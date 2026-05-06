"""
Maverick Agent HTTP API Server

Exposes the PAX Store provisioning workflow as a REST API
so N8N (or any webhook) can trigger it remotely.

Endpoints:
  POST /provision          — start a provisioning job (async)
  GET  /jobs/{job_id}      — check job status + result
  GET  /history            — recent run history from JSONL
  GET  /health             — health check

Run:
  pip install fastapi uvicorn
  uvicorn server:app --host 0.0.0.0 --port 8080

Or with auto-reload for development:
  uvicorn server:app --reload --port 8080
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title="Maverick Terminal Agent API",
    description="PAX Store provisioning automation via headless browser",
    version="1.0.0",
)

# In-memory job store (survives restarts via JSONL history)
_jobs: dict[str, dict] = {}

RUN_HISTORY_FILE = Path("tmp/run-history/paxstore_runs.jsonl")


# ── Request / Response models ────────────────────────────────────────────────

class ProvisionRequest(BaseModel):
    merchant_number: str
    pinpad_serial: str | None = None
    pos_serial: str | None = None
    pinpad_model: str = "A3700"
    pos_model: str = "L1400"
    var_v_number: str | None = None
    steps: str = "two-device"
    submit: bool = True
    activate_payment_app: bool = False


class JobStatus(BaseModel):
    job_id: str
    status: str           # "queued" | "running" | "success" | "failed"
    created_at: str
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None


# ── Background provisioning task ─────────────────────────────────────────────

async def _run_provisioning(job_id: str, req: ProvisionRequest) -> None:
    """Run the provisioning script as a subprocess and track the result."""
    _jobs[job_id]["status"] = "running"

    script = Path(__file__).parent / "scripts" / "paxstore_provision_from_pdf.py"

    cmd = [
        "python3", str(script),
        "--merchant-number", req.merchant_number,
        "--var-source", "kit-api",
        "--steps", req.steps,
    ]

    if req.pinpad_serial:
        cmd += ["--pinpad-serial", req.pinpad_serial, "--pinpad-model", req.pinpad_model]
    if req.pos_serial:
        cmd += ["--pos-serial", req.pos_serial, "--pos-model", req.pos_model]
    if req.var_v_number:
        cmd += ["--var-v-number", req.var_v_number]
    if req.submit:
        cmd.append("--submit")
    if req.activate_payment_app:
        cmd.append("--activate-payment-app")

    env = os.environ.copy()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd=str(Path(__file__).parent),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
        output = stdout.decode(errors="replace")

        if proc.returncode == 0:
            _jobs[job_id].update({
                "status": "success",
                "finished_at": datetime.now(UTC).isoformat(),
                "result": {"output": output[-4000:]},  # last 4000 chars
            })
        else:
            _jobs[job_id].update({
                "status": "failed",
                "finished_at": datetime.now(UTC).isoformat(),
                "error": output[-2000:],
            })
    except asyncio.TimeoutError:
        _jobs[job_id].update({
            "status": "failed",
            "finished_at": datetime.now(UTC).isoformat(),
            "error": "Provisioning timed out after 600 seconds",
        })
    except Exception as exc:
        _jobs[job_id].update({
            "status": "failed",
            "finished_at": datetime.now(UTC).isoformat(),
            "error": str(exc),
        })


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "agent": "maverick-terminal-agent"}


@app.post("/provision", response_model=JobStatus, status_code=202)
async def provision(req: ProvisionRequest, background_tasks: BackgroundTasks) -> JobStatus:
    """
    Start a PAX Store provisioning job.

    Returns immediately with a job_id. Poll GET /jobs/{job_id} for status.

    Example body:
    {
      "merchant_number": "201100305938",
      "pinpad_serial": "2290664794",
      "pinpad_model": "A3700",
      "submit": true
    }
    """
    if not req.pinpad_serial and not req.pos_serial:
        raise HTTPException(status_code=422, detail="Provide pinpad_serial or pos_serial")

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "request": req.model_dump(),
        "finished_at": None,
        "result": None,
        "error": None,
    }

    background_tasks.add_task(_run_provisioning, job_id, req)
    return JobStatus(**_jobs[job_id])


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str) -> JobStatus:
    """Check the status of a provisioning job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobStatus(**_jobs[job_id])


@app.get("/history")
def history(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent provisioning runs from the JSONL run history."""
    if not RUN_HISTORY_FILE.exists():
        return []
    lines = RUN_HISTORY_FILE.read_text(encoding="utf-8").strip().splitlines()
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return list(reversed(records))


@app.get("/history/check/{serial}")
def check_serial(serial: str) -> dict:
    """
    Check if a serial number was already successfully provisioned.
    Returns {provisioned: bool, last_run: dict | null}
    """
    if not RUN_HISTORY_FILE.exists():
        return {"provisioned": False, "last_run": None}

    lines = RUN_HISTORY_FILE.read_text(encoding="utf-8").strip().splitlines()
    successful_runs = []
    for line in lines:
        try:
            r = json.loads(line)
            serials = {r.get("pinpad_serial"), r.get("pos_serial"), r.get("serial_number")}
            if serial in serials and r.get("status") == "success" and r.get("submit") and not r.get("plan_only"):
                successful_runs.append(r)
        except json.JSONDecodeError:
            pass

    if successful_runs:
        return {"provisioned": True, "last_run": successful_runs[-1]}
    return {"provisioned": False, "last_run": None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
