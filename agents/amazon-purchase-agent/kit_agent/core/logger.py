"""
Structured logger — writes JSON lines + human-readable markdown per session.
Every onboarding gets its own log file. No data is lost.
"""
from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_config


class SessionLogger:
    def __init__(self, merchant_name: str):
        cfg = get_config()
        log_dir = Path(cfg["logging"]["dir"])
        log_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        slug = merchant_name.lower().replace(" ", "-").replace("/", "-")[:40]
        self.md_path = log_dir / f"{ts}_{slug}_onboarding.md"
        self.json_path = log_dir / f"{ts}_{slug}_onboarding.jsonl"

        self.merchant_name = merchant_name
        self.started_at = time.time()
        self.events: list[dict] = []
        self.step_timings: dict[str, float] = {}
        self._current_step: str | None = None
        self._step_start: float = 0.0

        self._init_md()

    # ── Public API ──────────────────────────────────────────────────────────

    def step(self, name: str) -> None:
        """Mark start of a named step."""
        if self._current_step:
            self._end_step()
        self._current_step = name
        self._step_start = time.time()
        self._event("step_start", {"step": name})
        self._md(f"\n## {name}\n")

    def info(self, msg: str, data: dict | None = None) -> None:
        self._event("info", {"msg": msg, **(data or {})})
        self._md(f"- {msg}" + (f"\n  ```\n  {json.dumps(data, indent=2)}\n  ```" if data else ""))

    def warn(self, msg: str, data: dict | None = None) -> None:
        self._event("warn", {"msg": msg, **(data or {})})
        self._md(f"- ⚠️  {msg}" + (f"  `{data}`" if data else ""))

    def error(self, msg: str, data: dict | None = None) -> None:
        self._event("error", {"msg": msg, **(data or {})})
        self._md(f"- ❌ {msg}" + (f"\n  ```\n  {json.dumps(data, indent=2)}\n  ```" if data else ""))

    def success(self, msg: str, data: dict | None = None) -> None:
        self._event("success", {"msg": msg, **(data or {})})
        self._md(f"- ✅ {msg}" + (f"  `{data}`" if data else ""))

    def extracted_profile(self, profile: dict) -> None:
        self._event("extracted_profile", profile)
        self._md(f"\n### Extracted Merchant Profile\n```json\n{json.dumps(profile, indent=2, default=str)}\n```\n")

    def finalize(self, status: str, application_id: int | None = None) -> None:
        if self._current_step:
            self._end_step()
        elapsed = time.time() - self.started_at
        summary = {
            "merchant": self.merchant_name,
            "application_id": application_id,
            "status": status,
            "duration_seconds": round(elapsed),
            "step_timings": {k: round(v, 1) for k, v in self.step_timings.items()},
        }
        self._event("session_end", summary)
        self._md(self._build_summary(summary))
        print(f"\n[LOG] Session log: {self.md_path}")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _event(self, kind: str, data: dict) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **data,
        }
        self.events.append(entry)
        with open(self.json_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def _md(self, text: str) -> None:
        with open(self.md_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def _init_md(self) -> None:
        self._md(
            f"# KIT Onboarding — {self.merchant_name}\n"
            f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )

    def _end_step(self) -> None:
        elapsed = time.time() - self._step_start
        self.step_timings[self._current_step] = elapsed
        self._current_step = None

    def _build_summary(self, s: dict) -> str:
        timings = "\n".join(f"| {k} | {v}s |" for k, v in s["step_timings"].items())
        return (
            f"\n---\n## Session Summary\n"
            f"| Field | Value |\n|---|---|\n"
            f"| Merchant | {s['merchant']} |\n"
            f"| Application ID | {s['application_id']} |\n"
            f"| Status | **{s['status']}** |\n"
            f"| Duration | {s['duration_seconds']}s |\n\n"
            f"### Step Timings\n| Step | Time |\n|---|---|\n{timings}\n"
        )
