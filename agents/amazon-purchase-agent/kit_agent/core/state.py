"""
SQLite-backed state machine — tracks every application across runs.
If the agent crashes mid-way, it can resume from the last successful step.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import get_config

STEPS = [
    "extract",
    "validate",
    "login",
    "check_existing",
    "create_application",
    "deployment",
    "business",
    "dba",
    "principal",
    "processing",
    "payment",
    "business_profile",
    "documents",
    "fees",
    "complete",
]


class ApplicationState:
    def __init__(self, pdf_path: str):
        cfg = get_config()
        db_path = Path(cfg["state"]["db_path"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self._ensure_schema()
        self.pdf_path = pdf_path
        self.row_id = self._get_or_create(pdf_path)

    # ── Public API ─────────────────────────────────────────────────────────

    def get(self, field: str) -> Any:
        row = self.conn.execute(
            f"SELECT {field} FROM applications WHERE id = ?", (self.row_id,)
        ).fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return row[0]
        return None

    def set(self, field: str, value: Any) -> None:
        serialized = json.dumps(value, default=str) if isinstance(value, (dict, list)) else value
        self.conn.execute(
            f"UPDATE applications SET {field} = ?, updated_at = ? WHERE id = ?",
            (serialized, datetime.utcnow().isoformat(), self.row_id),
        )
        self.conn.commit()

    def complete_step(self, step: str) -> None:
        completed = self.get("completed_steps") or []
        if step not in completed:
            completed.append(step)
        self.set("completed_steps", completed)
        self.set("current_step", step)

    def step_done(self, step: str) -> bool:
        return step in (self.get("completed_steps") or [])

    def set_profile(self, profile: dict) -> None:
        self.set("merchant_profile", profile)

    def get_profile(self) -> dict | None:
        return self.get("merchant_profile")

    def set_application_id(self, app_id: int) -> None:
        self.conn.execute(
            "UPDATE applications SET application_id = ?, updated_at = ? WHERE id = ?",
            (app_id, datetime.utcnow().isoformat(), self.row_id),
        )
        self.conn.commit()

    def get_application_id(self) -> int | None:
        row = self.conn.execute(
            "SELECT application_id FROM applications WHERE id = ?", (self.row_id,)
        ).fetchone()
        return row[0] if row else None

    def mark_failed(self, error: str) -> None:
        self.set("status", "failed")
        self.set("last_error", error)

    def mark_complete(self) -> None:
        self.set("status", "complete")

    # ── Schema ──────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pdf_path TEXT UNIQUE,
                application_id INTEGER,
                status TEXT DEFAULT 'pending',
                current_step TEXT,
                completed_steps TEXT,
                merchant_profile TEXT,
                last_error TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        self.conn.commit()

    def _get_or_create(self, pdf_path: str) -> int:
        row = self.conn.execute(
            "SELECT id FROM applications WHERE pdf_path = ?", (pdf_path,)
        ).fetchone()
        if row:
            return row[0]
        now = datetime.utcnow().isoformat()
        cur = self.conn.execute(
            "INSERT INTO applications (pdf_path, created_at, updated_at) VALUES (?, ?, ?)",
            (pdf_path, now, now),
        )
        self.conn.commit()
        return cur.lastrowid
