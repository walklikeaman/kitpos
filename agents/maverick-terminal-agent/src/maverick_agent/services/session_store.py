"""
Supabase-backed session storage for autonomous agents.

Stores Playwright `storage_state` JSON in the `agent_sessions` table so the
PAX Store provisioning script can reuse cookies across runs without writing
anything to the local filesystem. Required for stateless / containerized
deployments where the local `tmp/` directory does not persist.

Schema (run once in Supabase SQL editor):

    create table if not exists agent_sessions (
      key         text primary key,
      value       jsonb not null,
      updated_at  timestamptz not null default now()
    );

Env vars required:
    SUPABASE_URL — e.g. https://hoowbtzdzndvyihxhlpb.supabase.co
    SUPABASE_KEY — anon or service-role key

Usage:
    state = load_session("paxstore")          # → dict | None
    save_session("paxstore", storage_state)    # upserts
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request


def _ssl_ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


_SSL = _ssl_ctx()


def _config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set in environment "
            "to use Supabase session storage."
        )
    return url, key


def _headers(key: str, *, prefer: str | None = None) -> dict[str, str]:
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def load_session(key: str) -> dict | None:
    """Return the stored session JSON for the given key, or None if not found."""
    url, api_key = _config()
    qs = urllib.parse.urlencode({"key": f"eq.{key}", "select": "value"})
    req = urllib.request.Request(
        f"{url}/rest/v1/agent_sessions?{qs}",
        headers=_headers(api_key),
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL) as resp:
            rows = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Supabase load_session failed: {exc.code} {exc.read().decode(errors='replace')}") from exc

    if not rows:
        return None
    return rows[0].get("value")


def save_session(key: str, value: dict) -> None:
    """Upsert a session value under the given key."""
    url, api_key = _config()
    body = json.dumps([{"key": key, "value": value}]).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/agent_sessions",
        data=body,
        headers=_headers(api_key, prefer="resolution=merge-duplicates,return=minimal"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL):
            pass
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Supabase save_session failed: {exc.code} {exc.read().decode(errors='replace')}") from exc


def delete_session(key: str) -> None:
    """Remove a session (e.g. after auth failure)."""
    url, api_key = _config()
    qs = urllib.parse.urlencode({"key": f"eq.{key}"})
    req = urllib.request.Request(
        f"{url}/rest/v1/agent_sessions?{qs}",
        headers=_headers(api_key),
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL):
            pass
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise RuntimeError(f"Supabase delete_session failed: {exc.code}") from exc
