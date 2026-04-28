#!/usr/bin/env python3
"""
Direct onboarding script for B&B Chill and Blend.
Bypasses PDF extraction — profile is hardcoded from photos + user input.

Usage:
  python onboard_bb_chill.py             # triggers 2FA, saves state, prints verify_id
  python onboard_bb_chill.py --code 123456   # completes login + full onboarding
  python onboard_bb_chill.py --skip-login    # skip login (use saved session)
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path

# Add parent dir so kit_agent is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from kit_agent.core.config import get_config
from kit_agent.core.logger import SessionLogger
from kit_agent.core.api import KITClient, KITAPIError
from kit_agent.core.verifier import ApplicationVerifier
from kit_agent.core.reporter import build_telegram_report, print_telegram_report

# ── Merchant Profile ─────────────────────────────────────────────────────────

PROFILE = {
    "business_name_dba": "CHILL & BLEND",
    "legal_name": "B&B CHILL AND BLEND",
    "entity_type": "LLC",
    "business_address": {
        "street": "216 SUNSET PLAZA",
        "city": "ENID",
        "state": "OK",
        "zip": "73703",
    },
    "home_address": {
        "street": "801 HEDGE DR",
        "city": "OKLAHOMA CITY",
        "state": "OK",
        "zip": "73110",
    },
    "contact_person": {
        "first": "BLAL",
        "last": "ALSHOHATEE",
    },
    "email": "Blal021302@gmail.com",
    "phone": "5105298377",
    "ein": "41-3449517",
    "ssn": "612314430",
    "dob": "02/13/2002",
    "dl_number": "A289488678",   # Oklahoma Non-Driver ID
    "dl_state": "OK",
    "dl_expiration": "10/31/2029",
    "routing_number": "",   # MISSING — no check provided
    "account_number": "",   # MISSING
    "founded_date": "04/01/2026",
    "industry": "Grocery Store",
    "validation_flags": [
        "⚠️ Non-Driver ID used as DL# (A289488678, Oklahoma)",
        "⚠️ Banking info MISSING — no voided check provided",
        "⚠️ Driver License document not uploaded — no DL photo provided",
    ],
}

_STATE_FILE = Path("/tmp/kit_bb_chill_2fa.json")
_SESSION_FILE = Path.home() / ".kit_session.json"

# ── 2FA helpers ───────────────────────────────────────────────────────────────

def trigger_2fa(log: SessionLogger) -> tuple[str, str, str]:
    """
    POST credentials to KIT → get 2FA page → extract verify_id + csrf.
    Returns (verify_id, csrf, cookie_jar_json).
    """
    cfg = get_config()
    base = cfg["kit_dashboard"]["base_url"].rstrip("/")
    login_url = base + cfg["kit_dashboard"]["login_path"]
    creds = cfg["credentials"]

    s = requests.Session()
    s.headers.update(cfg["kit_dashboard"].get("default_headers", {}))

    # GET login page for initial CSRF
    r = s.get(login_url, timeout=30)
    csrf_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', r.text) \
          or re.search(r'name="_csrf"[^>]+value="([^"]+)"', r.text)
    if not csrf_m:
        raise KITAPIError("No CSRF on login page")
    csrf1 = csrf_m.group(1)

    # POST credentials
    resp = s.post(login_url, data={
        "_csrf": csrf1,
        "LoginForm[username]": creds["email"],
        "LoginForm[password]": creds["password"],
        "LoginForm[rememberMe]": "1",
    }, allow_redirects=True, timeout=30)

    # Check if we're already logged in (no 2FA needed)
    if resp.url.rstrip("/").endswith("/site/login") is False:
        log.success("No 2FA required — session valid")
        # Save session
        cookie_data = [
            {"name": c.name, "value": c.value,
             "domain": c.domain or "kitdashboard.com", "path": c.path or "/"}
            for c in s.cookies
        ]
        _save_2fa_state({
            "verify_id": None,
            "csrf2": None,
            "cookies": cookie_data,
            "no_2fa": True,
        })
        return None, None, json.dumps(cookie_data)

    # We need 2FA
    vid_m = re.search(r'LoginForm\[twoStepVerificationId\][^>]+value="([^"]+)"', resp.text)
    if not vid_m:
        raise KITAPIError("2FA page detected but no twoStepVerificationId found")

    verify_id = vid_m.group(1)
    csrf2_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text) \
           or re.search(r'name="_csrf"[^>]+value="([^"]+)"', resp.text)
    csrf2 = csrf2_m.group(1) if csrf2_m else csrf1

    cookie_data = [
        {"name": c.name, "value": c.value,
         "domain": c.domain or "kitdashboard.com", "path": c.path or "/"}
        for c in s.cookies
    ]
    _save_2fa_state({
        "verify_id": verify_id,
        "csrf2": csrf2,
        "cookies": cookie_data,
        "no_2fa": False,
        "email": creds["email"],
        "password": creds["password"],
    })
    return verify_id, csrf2, json.dumps(cookie_data)


def complete_2fa(code: str, log: SessionLogger) -> KITClient:
    """Submit 2FA code using saved state, return authenticated KITClient."""
    state = _load_2fa_state()
    cfg = get_config()
    base = cfg["kit_dashboard"]["base_url"].rstrip("/")
    login_url = base + cfg["kit_dashboard"]["login_path"]

    client = KITClient(log)

    if state.get("no_2fa"):
        log.success("Restoring session (no 2FA was needed)")
        for c in state["cookies"]:
            client._s.cookies.set(c["name"], c["value"],
                                  domain=c.get("domain", "kitdashboard.com"),
                                  path=c.get("path", "/"))
        # Get CSRF
        r = client._s.get(base + cfg["kit_dashboard"]["application_list_path"], timeout=30)
        client._csrf = client._extract_csrf(r.text)
        return client

    # Restore cookies into client session
    for c in state["cookies"]:
        client._s.cookies.set(c["name"], c["value"],
                              domain=c.get("domain", "kitdashboard.com"),
                              path=c.get("path", "/"))

    resp = client._s.post(login_url, data={
        "_csrf": state["csrf2"],
        "LoginForm[twoStepVerificationId]": state["verify_id"],
        "LoginForm[username]": state["email"],
        "LoginForm[password]": state["password"],
        "LoginForm[verificationCode]": code.strip(),
        "LoginForm[rememberMe]": "1",
    }, allow_redirects=True, timeout=30)

    if resp.url.rstrip("/").endswith("/site/login"):
        raise KITAPIError(f"2FA rejected — still on login page. URL={resp.url}")

    client._csrf = client._extract_csrf(resp.text)
    # Save good session
    session_data = [
        {"name": c.name, "value": c.value,
         "domain": c.domain or "kitdashboard.com", "path": c.path or "/"}
        for c in client._s.cookies
    ]
    _SESSION_FILE.write_text(json.dumps(session_data))
    log.success(f"2FA complete — logged in. Redirected to: {resp.url}")
    return client


def _save_2fa_state(data: dict) -> None:
    _STATE_FILE.write_text(json.dumps(data))


def _load_2fa_state() -> dict:
    if not _STATE_FILE.exists():
        raise FileNotFoundError("2FA state not found. Run without --code first.")
    return json.loads(_STATE_FILE.read_text())


# ── Onboarding steps ──────────────────────────────────────────────────────────

def run_onboarding(client: KITClient, log: SessionLogger) -> dict:
    cfg = get_config()

    # Step: find or create application
    log.step("Check for orphan draft / Create application")
    html = client._get_html(
        client.base + cfg["kit_dashboard"]["application_list_path"],
        label="application list"
    )

    # Look for "No Set" rows
    app_id = None
    no_set_matches = re.findall(
        r'"edit.*?id=(\d+).*?No\s+Set',
        html, re.DOTALL | re.I
    )
    # Also try another pattern
    if not no_set_matches:
        # Try data-key or href patterns near "No Set"
        blocks = re.findall(r'(\d{5,7})[^<]*No Set', html)
        if blocks:
            no_set_matches = blocks

    if no_set_matches:
        app_id = int(no_set_matches[0])
        log.info(f"Found existing draft app #{app_id} — reusing it")
    else:
        log.info("No orphan draft found — creating new application")
        campaign_id = client.get_campaign_id("KIT POS", "Kit POS InterCharge Plus")
        app_id = client.create_application(campaign_id)

    token = client.get_application_token(app_id)
    log.info(f"App ID={app_id}, token={token[:8]}...")

    # Step: Deployment
    log.step("Deployment")
    client.submit_deployment(app_id, token)

    # Step: Business / Corporate
    log.step("Business / Corporate / DBA")
    client.submit_business(app_id, token, PROFILE)

    # Step: Principal
    log.step("Principal")
    # Override DL state in principal call — use state_id directly
    client.submit_principal(app_id, token, PROFILE)

    # Step: Processing (skip — no banking data)
    log.warn("Skipping banking step — routing/account numbers not available")

    # Step: Payment
    log.step("Payment information")
    client.submit_payment(app_id, token, PROFILE)

    # Step: Business Profile
    log.step("Business profile")
    client.submit_business_profile(app_id, token)

    # Step: Documents (skip — no check or DL PDF)
    log.warn("Skipping document upload — no check PDF, no DL PDF provided")

    # Refresh token before verify
    token = client.get_application_token(app_id)

    # Step: Verify
    log.step("Verifying application")
    verifier = ApplicationVerifier(client, log)
    verification = verifier.verify_all_steps(app_id, token)

    # Step: Report
    report = build_telegram_report(PROFILE, app_id, verification, check_images=None)
    print_telegram_report(report)

    return {"report": report, "profile": PROFILE, "app_id": app_id}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", help="2FA verification code from email")
    parser.add_argument("--skip-login", action="store_true",
                        help="Skip login — reuse saved .kit_session.json")
    args = parser.parse_args()

    log = SessionLogger("bb_chill_blend")

    if args.skip_login:
        log.info("Skip-login mode — reusing saved session")
        client = KITClient(log)
        cfg = get_config()
        if _SESSION_FILE.exists():
            for c in json.loads(_SESSION_FILE.read_text()):
                client._s.cookies.set(c["name"], c["value"],
                                      domain=c.get("domain", "kitdashboard.com"),
                                      path=c.get("path", "/"))
        r = client._s.get(
            client.base + cfg["kit_dashboard"]["application_list_path"],
            timeout=30
        )
        if "login" in r.url.lower():
            log.error("Session expired — cannot skip login. Run without --skip-login.")
            sys.exit(1)
        client._csrf = client._extract_csrf(r.text)
        log.success("Session valid")
        run_onboarding(client, log)
        return

    if args.code:
        # Complete 2FA + run full onboarding
        client = complete_2fa(args.code, log)
        run_onboarding(client, log)
    else:
        # Trigger 2FA, save state, print verify_id
        log.info("Triggering 2FA login...")
        verify_id, csrf2, _ = trigger_2fa(log)
        if verify_id is None:
            # No 2FA needed — session still valid, just run
            log.info("No 2FA needed — session still valid, running onboarding...")
            client = complete_2fa(None, log)
            run_onboarding(client, log)
        else:
            print(f"\n{'='*60}")
            print(f"2FA REQUIRED")
            print(f"verify_id: {verify_id}")
            print(f"Check nikita@kit-pos.com for verification code.")
            print(f"Then run: python onboard_bb_chill.py --code <CODE>")
            print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
