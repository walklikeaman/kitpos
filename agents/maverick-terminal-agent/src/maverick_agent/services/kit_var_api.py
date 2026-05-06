"""
KIT Dashboard VAR API client.

Fetches VAR (TSYS parameters) directly from the KIT Dashboard REST API
using a Bearer token — no browser, no PDF, no cross-agent imports.

Base URL: https://dashboard.maverickpayments.com/api
Auth:     Authorization: Bearer <KIT_API_KEY>
Docs:     https://developers.kitdashboard.com/#/dashboard

⚠️ Cloudflare blocks Python default User-Agent.
   Always send a browser-like UA (already set in _HEADERS).

Key flow for "get VAR by MID":
  1. GET /merchant?filter[company.mid][eq]={mid}  → find merchant internal ID
  2. GET /terminal?filter[merchant.id][eq]={id}   → list terminals
  3. GET /terminal/{terminal_id}/var-list          → VAR JSON for one terminal
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

_BASE = "https://dashboard.maverickpayments.com/api"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


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


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": _UA,
        "Referer": "https://kitdashboard.com/",
        "Origin": "https://kitdashboard.com",
    }


def _get(path: str, params: dict, api_key: str) -> dict:
    qs = urllib.parse.urlencode(params)
    url = f"{_BASE}{path}{'?' + qs if qs else ''}"
    req = urllib.request.Request(url, headers=_headers(api_key))
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"KIT API {exc.code} {path}: {body}") from exc


# ── Field mapping: /terminal/{id}/var-list → our dict format ─────────────────

def _parse_var_response(raw: dict) -> dict:
    """
    Convert /terminal/{id}/var-list response to the flat dict format
    used by PaxProvisioningData.from_api_var().

    Fields returned match what kit-dashboard-merchant-data returns from var_data_by_mid().
    """
    addr = raw.get("address") or {}
    dba_obj = raw.get("dba") or {}
    v_number = str(raw.get("backendProcessorId", ""))

    return {
        "dba":             dba_obj.get("name", ""),
        "mid":             str(raw.get("merchantNumber", "")),
        "bin":             raw.get("bin", ""),
        "chain":           raw.get("chain", ""),
        "agent_bank":      raw.get("agentBank", ""),
        "mcc":             str(raw.get("mcc", "")),
        "store_number":    raw.get("storeNumber", ""),
        "terminal_number": str(raw.get("tid", "")),
        "city":            addr.get("city", ""),
        "state":           addr.get("state", ""),
        "zip":             addr.get("zip", ""),
        "v_number":        v_number,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def var_rows_by_mid(
    merchant_number: str,
    api_key: str,
) -> list[dict]:
    """
    Return all VAR rows for a merchant identified by 12-digit MID.

    Steps:
      1. Find merchant by MID via /merchant search
      2. List all terminals for that merchant
      3. Fetch /var-list for each terminal

    Returns list of dicts in the same format as kit-dashboard-merchant-data.
    Returns [] if merchant not found or has no terminals.
    """
    mid_int = int(merchant_number)

    # Step 1: find merchant internal ID by MID
    merchant_id = _find_merchant_id_by_mid(mid_int, api_key)
    if merchant_id is None:
        return []

    # Step 2: list terminals
    terminals = _get_terminals(merchant_id, api_key)
    if not terminals:
        return []

    # Step 3: fetch VAR for each terminal
    rows = []
    for terminal in terminals:
        tid = terminal.get("id")
        if not tid:
            continue
        try:
            raw = _get(f"/terminal/{tid}/var-list", {}, api_key)
            rows.append(_parse_var_response(raw))
        except RuntimeError:
            continue

    return rows


def _find_merchant_id_by_mid(mid_int: int, api_key: str) -> int | None:
    """
    Search merchants page-by-page until we find one whose terminal MID matches.
    Uses /terminal endpoint with MID filter for efficiency.
    """
    # Direct terminal search by merchantNumber is faster than scanning merchants
    data = _get("/terminal", {"filter[merchantNumber][eq]": mid_int, "per-page": 10}, api_key)
    items = data.get("items") or data.get("data") or []
    if items:
        merchant = items[0].get("merchant") or {}
        return merchant.get("id")

    # Fallback: scan merchants page-by-page
    page = 1
    while True:
        data = _get("/merchant", {"per-page": 50, "page": page}, api_key)
        for item in (data.get("items") or data.get("data") or []):
            for dba in item.get("dbas") or []:
                proc = dba.get("processing") or {}
                if int(proc.get("mid", 0)) == mid_int:
                    return item["id"]
        meta = data.get("_meta") or data.get("meta") or {}
        if page >= int(meta.get("pageCount", meta.get("last_page", 1))):
            break
        page += 1

    return None


def _get_terminals(merchant_id: int, api_key: str) -> list[dict]:
    data = _get("/terminal", {"filter[merchant.id][eq]": merchant_id, "per-page": 50}, api_key)
    return data.get("items") or data.get("data") or []
