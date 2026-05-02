"""
Run logger for KIT Dashboard onboarding agent.

Writes append-only JSONL logs to runs/runs.jsonl so every onboarding attempt
(success or failure) is permanently recorded and reusable for learning.

Usage:
    from merchant_data.services.run_logger import RunLogger

    log = RunLogger()
    log.success(
        merchant_name="El Camino Mart Inc",
        app_id=756692,
        source_pdf="El Camino Mart Inc.pdf",
        notes="DL + voided check uploaded",
    )

    log.failure(
        merchant_name="Some Merchant",
        source_pdf="file.pdf",
        reason="Could not parse EIN from PDF",
        error="re.search returned None on page 1",
    )
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RUNS_DIR = Path(__file__).parent.parent.parent.parent / "runs"
_RUNS_FILE = _RUNS_DIR / "runs.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunLogger:
    def __init__(self, runs_file: Path | None = None) -> None:
        self.runs_file = runs_file or _RUNS_FILE
        self.runs_file.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, entry: dict[str, Any]) -> None:
        with open(self.runs_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def success(
        self,
        merchant_name: str,
        app_id: int,
        source_pdf: str = "",
        principal_name: str = "",
        entity_type: str = "",
        documents: list[str] | None = None,
        notes: str = "",
        **extra: Any,
    ) -> None:
        """Log a successful onboarding run."""
        entry = {
            "status": "SUCCESS",
            "timestamp": _now(),
            "merchant_name": merchant_name,
            "app_id": app_id,
            "app_url": f"https://kitdashboard.com/boarding-application/{app_id}",
            "source_pdf": source_pdf,
            "principal_name": principal_name,
            "entity_type": entity_type,
            "documents": documents or [],
            "notes": notes,
            **extra,
        }
        self._write(entry)
        print(f"[RunLogger] ✅ SUCCESS logged: {merchant_name} → app_id={app_id}")

    def failure(
        self,
        merchant_name: str,
        source_pdf: str = "",
        reason: str = "",
        error: str = "",
        app_id: int | None = None,
        notes: str = "",
        **extra: Any,
    ) -> None:
        """Log a failed onboarding run with root cause."""
        entry = {
            "status": "FAILURE",
            "timestamp": _now(),
            "merchant_name": merchant_name,
            "app_id": app_id,
            "source_pdf": source_pdf,
            "reason": reason,
            "error": error,
            "notes": notes,
            **extra,
        }
        self._write(entry)
        print(f"[RunLogger] ❌ FAILURE logged: {merchant_name} — {reason}")

    def list_runs(self, status: str | None = None) -> list[dict[str, Any]]:
        """Read all logged runs, optionally filtered by status ('SUCCESS'/'FAILURE')."""
        if not self.runs_file.exists():
            return []
        runs = []
        with open(self.runs_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if status is None or entry.get("status") == status:
                        runs.append(entry)
                except json.JSONDecodeError:
                    continue
        return runs

    def summary(self) -> str:
        """Print a human-readable summary of all runs."""
        runs = self.list_runs()
        if not runs:
            return "No runs logged yet."
        successes = [r for r in runs if r["status"] == "SUCCESS"]
        failures = [r for r in runs if r["status"] == "FAILURE"]
        lines = [
            f"Total runs: {len(runs)}  ✅ {len(successes)} success  ❌ {len(failures)} failures",
            "",
        ]
        for r in runs:
            icon = "✅" if r["status"] == "SUCCESS" else "❌"
            merchant = r.get("merchant_name", "?")
            ts = r.get("timestamp", "?")[:10]
            detail = f"app_id={r['app_id']}" if r.get("app_id") else r.get("reason", "")
            lines.append(f"  {icon} {ts}  {merchant:<40} {detail}")
        return "\n".join(lines)
