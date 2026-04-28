"""
Config loader — merges config.yaml with environment variable overrides.
No values are hard-coded here; all defaults live in config.yaml.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent


def load_config() -> dict[str, Any]:
    load_dotenv(_ROOT / ".env", override=False)

    with open(_ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Environment variable overrides (KIT_BASE_URL → kit_dashboard.base_url, etc.)
    _apply_env_overrides(cfg)
    return cfg


def _apply_env_overrides(cfg: dict) -> None:
    mapping = {
        "KIT_BASE_URL":    ("kit_dashboard", "base_url"),
        "KIT_EMAIL":       ("credentials", "email"),
        "KIT_PASSWORD":    ("credentials", "password"),
        "ANTHROPIC_API_KEY": ("anthropic", "api_key"),
        "LOG_DIR":         ("logging", "dir"),
        "DB_PATH":         ("state", "db_path"),
    }
    for env_key, (section, field) in mapping.items():
        val = os.getenv(env_key)
        if val:
            cfg.setdefault(section, {})[field] = val

    # Pull credentials from top-level env if not set via yaml
    if "credentials" not in cfg:
        cfg["credentials"] = {}
    cfg["credentials"].setdefault("email", os.getenv("KIT_EMAIL", ""))
    cfg["credentials"].setdefault("password", os.getenv("KIT_PASSWORD", ""))
    cfg.setdefault("anthropic", {})["api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
    cfg.setdefault("logging", {}).setdefault("dir", str(_ROOT.parent / "logs"))
    cfg.setdefault("state", {}).setdefault("db_path", str(_ROOT.parent / "kit_agent.db"))


# Singleton
_config: dict | None = None


def get_config() -> dict[str, Any]:
    global _config
    if _config is None:
        _config = load_config()
    return _config
