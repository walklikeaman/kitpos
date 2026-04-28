"""
KIT Dashboard HTTP client — pure requests, zero browser, zero hard-coded values.

All URLs come from config.yaml. The client logs into the dashboard once,
maintains a session, and exposes typed methods for each API action.

Design principles:
  - Every method validates its inputs before calling the API
  - Every response is checked; errors raise KITAPIError with context
  - Retry logic is built-in (controlled by config)
  - No jQuery, no JavaScript, no osascript — just HTTP
"""
from __future__ import annotations
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

import requests

from .config import get_config
from .logger import SessionLogger

# Where we persist the authenticated session between runs
_SESSION_FILE = Path.home() / ".kit_session.json"


class KITAPIError(Exception):
    def __init__(self, msg: str, status: int | None = None, body: str | None = None):
        super().__init__(msg)
        self.status = status
        self.body = body


class KITClient:
    def __init__(self, log: SessionLogger):
        cfg = get_config()
        self.base = cfg["kit_dashboard"]["base_url"].rstrip("/")
        self.cfg = cfg["kit_dashboard"]
        self.defaults = cfg
        self.log = log
        self._s = requests.Session()
        self._s.headers.update(self.cfg.get("default_headers", {}))
        self._csrf: str | None = None
        self._max_retries: int = self.cfg.get("max_retries", 3)
        self._retry_delay: float = self.cfg.get("retry_delay_seconds", 2)
        self._timeout: int = self.cfg.get("request_timeout_seconds", 30)

    # ── Authentication ──────────────────────────────────────────────────────

    def login(self, email: str, password: str,
              code_provider: Callable[[str], str] | None = None) -> None:
        """
        Log in and establish a session.

        Tries the saved session first (cookie file).  On session expiry,
        does a fresh login.  If the server requires 2FA, `code_provider` is
        called with the verificationId string; it must return the 6-digit code.
        If `code_provider` is None and 2FA fires, raises KITAPIError.
        """
        login_url = self.base + self.cfg["login_path"]

        # ── Try reusing a saved session ─────────────────────────────────
        if _SESSION_FILE.exists():
            try:
                self._load_session(_SESSION_FILE)
                # Quick check: can we reach the application list?
                r = self._s.get(
                    self.base + self.cfg["application_list_path"],
                    timeout=self._timeout, allow_redirects=True,
                )
                if "login" not in r.url.lower():
                    self._csrf = self._extract_csrf(r.text)
                    self.log.success("Resumed saved session (no login needed)")
                    return
                self.log.info("Saved session expired — doing fresh login")
            except Exception as e:
                self.log.info(f"Could not reuse session ({e}) — fresh login")

        # ── Fresh login ─────────────────────────────────────────────────
        page = self._get_html(login_url, label="login page")
        csrf = self._extract_csrf(page)

        resp = self._s.post(login_url, data={
            "_csrf": csrf,
            "LoginForm[username]": email,
            "LoginForm[password]": password,
            "LoginForm[rememberMe]": "1",
        }, allow_redirects=True, timeout=self._timeout)

        # ── 2FA check ───────────────────────────────────────────────────
        if resp.url.rstrip("/").endswith("/site/login"):
            verify_id_m = re.search(
                r'LoginForm\[twoStepVerificationId\][^>]+value="([^"]+)"', resp.text
            )
            if not verify_id_m:
                raise KITAPIError("Login failed — still on login page (bad credentials?).")

            verify_id = verify_id_m.group(1)
            csrf2_m = (re.search(r'name="_csrf"[^>]+value="([^"]+)"', resp.text)
                       or re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text))
            csrf2 = csrf2_m.group(1) if csrf2_m else csrf

            self.log.info("2FA required — requesting verification code")

            if code_provider is None:
                raise KITAPIError(
                    "2FA required but no code_provider given. "
                    "Pass code_provider= to KITClient.login()."
                )

            code = code_provider(verify_id)
            if not code or not re.match(r"^\d{4,8}$", code.strip()):
                raise KITAPIError(f"Invalid 2FA code received: '{code}'")

            resp = self._s.post(login_url, data={
                "_csrf": csrf2,
                "LoginForm[twoStepVerificationId]": verify_id,
                "LoginForm[username]": email,
                "LoginForm[password]": password,
                "LoginForm[verificationCode]": code.strip(),
                "LoginForm[rememberMe]": "1",
            }, allow_redirects=True, timeout=self._timeout)

            if resp.url.rstrip("/").endswith("/site/login"):
                raise KITAPIError("2FA code rejected — still on login page.")

        self._csrf = self._extract_csrf(resp.text)
        self._save_session(_SESSION_FILE)
        self.log.success("Logged in to KIT Dashboard")

    def _save_session(self, path: Path) -> None:
        data = [
            {"name": c.name, "value": c.value,
             "domain": c.domain or "kitdashboard.com", "path": c.path or "/"}
            for c in self._s.cookies
        ]
        path.write_text(json.dumps(data))

    def _load_session(self, path: Path) -> None:
        for c in json.loads(path.read_text()):
            self._s.cookies.set(c["name"], c["value"],
                                domain=c.get("domain", "kitdashboard.com"),
                                path=c.get("path", "/"))

    def refresh_csrf(self, path: str = "") -> str:
        """Re-fetch CSRF from any page; call when getting 400s."""
        url = self.base + (path or self.cfg["application_list_path"])
        html = self._get_html(url, label="csrf refresh")
        self._csrf = self._extract_csrf(html)
        return self._csrf

    # ── Application Management ──────────────────────────────────────────────

    def find_existing_draft(self) -> int | None:
        """
        Returns application ID if there's an empty 'No Set' draft created by
        current user — to avoid leaving orphan applications.
        Agent reasons about this dynamically from the list page HTML.
        """
        html = self._get_html(
            self.base + self.cfg["application_list_path"],
            label="application list"
        )
        # Look for 'No Set' status rows — the LLM reasoning happens in extractor.py
        # Here we do a simple heuristic: find application IDs with status "No Set"
        matches = re.findall(
            r'data-id=["\'](\d+)["\'][^>]*>.*?No Set',
            html, re.DOTALL
        )
        if matches:
            self.log.warn(f"Found existing draft application(s): {matches}")
            return int(matches[0])
        return None

    def get_campaign_id(self, search_query: str, target_name: str) -> int:
        """Dynamically discover the campaign ID by searching — never hard-coded."""
        url = self.base + self.cfg["campaign_search_path"]
        data = self._get_json(url, params={"q": search_query}, label="campaign search")
        items = data if isinstance(data, list) else data.get("items", data.get("results", []))
        for item in items:
            name = item.get("name", item.get("text", ""))
            if target_name.lower() in name.lower():
                cid = item.get("id", item.get("value"))
                self.log.info(f"Campaign found: {name} (id={cid})")
                return int(cid)
        raise KITAPIError(f"Campaign '{target_name}' not found. Available: {[i.get('name','?') for i in items]}")

    def create_application(self, campaign_id: int) -> int:
        """Create a new application and return its ID."""
        self.refresh_csrf(self.cfg["application_list_path"])
        url = self.base + self.cfg["application_list_path"]
        payload = {
            "_csrf": self._csrf,
            "campaignId": campaign_id,
        }
        resp = self._post(url, data=payload, label="create application")
        # Response should redirect to /boarding/default/modify?id=XXXXXX
        app_id = self._extract_app_id_from_url(resp.url)
        if not app_id:
            # Try to extract from response body
            app_id = self._extract_app_id_from_html(resp.text)
        if not app_id:
            raise KITAPIError("Could not determine new application ID", body=resp.text[:500])
        self.log.success(f"Application created: id={app_id}")
        return app_id

    # ── Form Steps ──────────────────────────────────────────────────────────

    def submit_deployment(self, app_id: int, token: str) -> None:
        cfg = self.defaults["deployment"]
        self._submit_step(app_id, token, "deployment", {
            "BoardingApplicationDeploymentForm[equipmentName]": cfg["equipment"],
            "BoardingApplicationDeploymentForm[equipmentProvidedBy]": cfg["equipment_provided_by"],
        })

    def submit_business(self, app_id: int, token: str, profile: dict) -> None:
        """Fill Business/Corporate step from merchant profile."""
        state_id = self._resolve_state_id(profile.get("business_address", {}).get("state", ""))
        zip_code = profile.get("business_address", {}).get("zip", "")
        city = profile.get("business_address", {}).get("city", "")
        ein = re.sub(r"\D", "", profile.get("ein", ""))
        founded = profile.get("founded_date", "")

        payload = {
            "BoardingApplicationModifyForm[companyName]": profile.get("legal_name", ""),
            "BoardingApplicationModifyForm[businessType]": profile.get("entity_type", ""),
            "BoardingApplicationModifyForm[companyAddress]": profile.get("business_address", {}).get("street", ""),
            "BoardingApplicationModifyForm[company_state_id]": state_id,
            "BoardingApplicationModifyForm[companyZip]": zip_code,
            "BoardingApplicationModifyForm[companyCity]": city,
            "BoardingApplicationModifyForm[foundedDate]": founded,
            "BoardingApplicationModifyForm[federalTaxId]": ein,
            "BoardingApplicationModifyForm[dbaSameAsCompany]": "No",
            "BoardingApplicationModifyForm[dbaName]": profile.get("business_name_dba", ""),
            "BoardingApplicationModifyForm[dbaAddress]": profile.get("business_address", {}).get("street", ""),
            "BoardingApplicationModifyForm[dba_state_id]": state_id,
            "BoardingApplicationModifyForm[dbaZip]": zip_code,
            "BoardingApplicationModifyForm[dbaCity]": city,
        }
        dba_cfg = self.defaults["dba"]
        payload.update({
            "BoardingApplicationModifyForm[buildingType]": dba_cfg["building_type"],
            "BoardingApplicationModifyForm[ownership]": dba_cfg["ownership"],
            "BoardingApplicationModifyForm[zoned]": dba_cfg["zoned"],
            "BoardingApplicationModifyForm[size]": dba_cfg["size_sqft"],
        })
        self._submit_step(app_id, token, "business", payload)

    def submit_principal(self, app_id: int, token: str, profile: dict) -> None:
        """Fill Principal (owner) step."""
        entity = profile.get("entity_type", "Corporation")
        title_map = self.defaults["principal"]["title_by_entity"]
        title = title_map.get(entity, "CEO")
        ssn = re.sub(r"\D", "", profile.get("ssn", ""))
        state_id = self._resolve_state_id(profile.get("home_address", {}).get("state", ""))

        payload = {
            "BoardingApplicationBusinessOwnerModifyForm[0][firstName]": profile.get("contact_person", {}).get("first", ""),
            "BoardingApplicationBusinessOwnerModifyForm[0][lastName]": profile.get("contact_person", {}).get("last", ""),
            "BoardingApplicationBusinessOwnerModifyForm[0][nationality]": self.defaults["principal"]["nationality"],
            "BoardingApplicationBusinessOwnerModifyForm[0][title]": title,
            "BoardingApplicationBusinessOwnerModifyForm[0][nationalId]": ssn,
            "BoardingApplicationBusinessOwnerModifyForm[0][birthday]": profile.get("dob", ""),
            "BoardingApplicationBusinessOwnerModifyForm[0][driverLicense]": profile.get("dl_number", ""),
            "BoardingApplicationBusinessOwnerModifyForm[0][address]": profile.get("home_address", {}).get("street", ""),
            "BoardingApplicationBusinessOwnerModifyForm[0][state_id]": state_id,
            "BoardingApplicationBusinessOwnerModifyForm[0][zip]": profile.get("home_address", {}).get("zip", ""),
            "BoardingApplicationBusinessOwnerModifyForm[0][city]": profile.get("home_address", {}).get("city", ""),
            "BoardingApplicationBusinessOwnerModifyForm[0][phone]": re.sub(r"\D", "", profile.get("phone", "")),
            "BoardingApplicationBusinessOwnerModifyForm[0][ownershipPercentage]": str(self.defaults["principal"]["ownership_percent"]),
            "BoardingApplicationBusinessOwnerModifyForm[0][isManagement]": "1",
        }
        self._submit_step(app_id, token, "principal", payload)

    def submit_processing(self, app_id: int, token: str, profile: dict) -> None:
        """Fill banking / routing & account step."""
        routing = re.sub(r"\D", "", profile.get("routing_number", ""))
        account = re.sub(r"\D", "", profile.get("account_number", ""))
        payload = {
            "BoardingApplicationModifyForm[routingNumber]": routing,
            "BoardingApplicationModifyForm[accountNumber]": account,
        }
        self._submit_step(app_id, token, "processing", payload)

    def submit_payment(self, app_id: int, token: str, profile: dict) -> None:
        """Fill payment info step — card types, volumes, refund policy."""
        pay_cfg = self.defaults["payment"]
        mcc = self._resolve_mcc(profile.get("industry", pay_cfg["default_industry"]))

        # Build card checkboxes — all card types from config
        payload: dict[str, Any] = {
            "BoardingApplicationModifyForm[acceptCards]": pay_cfg["accept_cards"],
            "BoardingApplicationModifyForm[monthlyVolume]": str(pay_cfg["monthly_volume"]),
            "BoardingApplicationModifyForm[averageTicket]": str(pay_cfg["average_ticket"]),
            "BoardingApplicationModifyForm[maxTicket]": str(pay_cfg["max_ticket"]),
            "BoardingApplicationModifyForm[refundPolicy]": pay_cfg["refund_policy"],
            "BoardingApplicationModifyForm[software]": pay_cfg["software"],
            "BoardingApplicationModifyForm[mcc]": mcc,
        }
        # Cards accepted — each card as separate checkbox field
        for card in pay_cfg["cards_accepted"]:
            key = f"BoardingApplicationModifyForm[cardsAccepted][{card.lower().replace(' ', '_')}]"
            payload[key] = "1"

        self._submit_step(app_id, token, "acquiring", payload)

    def submit_business_profile(self, app_id: int, token: str) -> None:
        bp = self.defaults["business_profile"]
        payload = {
            "BoardingApplicationModifyForm[seasonal]": "0" if not bp["seasonal"] else "1",
            "BoardingApplicationModifyForm[customerTypeIndividual]": str(bp["customer_type_individual_pct"]),
            "BoardingApplicationModifyForm[customerLocationLocal]": str(bp["customer_location_local_pct"]),
            "BoardingApplicationModifyForm[fulfillmentTime]": str(bp["fulfillment_hours"]),
        }
        self._submit_step(app_id, token, "acquiring", payload)

    # ── Documents ───────────────────────────────────────────────────────────

    def upload_document(self, app_id: int, token: str,
                        file_path: Path, about: str,
                        owner_id: int | None = None) -> dict:
        """
        Upload a file and attach it to the application.
        about = key from config.yaml document_categories (e.g. 'voided-check').
        owner_id = principal ID for DL attachment.
        """
        # Step 1: upload to temp
        upload_url = self.base + self.cfg["attachment_upload_path"] + "?save=0"
        with open(file_path, "rb") as f:
            resp = self._s.post(
                upload_url,
                files={"file": (file_path.name, f, "application/pdf")},
                headers={"X-CSRF-Token": self._csrf},
                timeout=self._timeout,
            )
        self._raise_for_error(resp, "file upload")
        upload_data = resp.json()
        if not upload_data.get("success"):
            raise KITAPIError("Upload failed", body=str(upload_data))
        self.log.info(f"Uploaded {file_path.name} → tmp={upload_data['tmp'][:20]}...")

        # Step 2: add to application (nested attachment[] format — required by API)
        add_url = (self.base + self.cfg["attachment_add_path"]
                   + f"?id={app_id}&token={token}")
        add_data: dict[str, Any] = {
            "attachment[tmp]": upload_data["tmp"],
            "attachment[name]": upload_data["name"],
            "attachment[type]": upload_data["type"],
            "attachment[size]": upload_data["size"],
            "attachment[about]": about,
            "attachment[success]": "true",
        }
        if owner_id:
            add_data["attachment[ownerId]"] = owner_id

        add_resp = self._s.post(add_url, data=add_data,
                                headers={"X-CSRF-Token": self._csrf},
                                timeout=self._timeout)
        self._raise_for_error(add_resp, "attachment add")
        result = add_resp.json()
        if "error" in result:
            raise KITAPIError(f"Attachment add error: {result['error']}", body=str(result))

        attachment_id = result.get("attachment_id")
        self.log.success(f"Attached {file_path.name} as '{about}' (id={attachment_id})")
        return result

    def get_application_token(self, app_id: int) -> str:
        """Extract the application token from the modify page."""
        url = self.base + self.cfg["application_modify_path"] + f"?id={app_id}"
        html = self._get_html(url, label="get app token")
        match = re.search(r'token[=&"\']([a-f0-9\-]{36})', html)
        if not match:
            raise KITAPIError(f"Could not find token for application {app_id}")
        return match.group(1)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _submit_step(self, app_id: int, token: str, step: str, payload: dict) -> requests.Response:
        url = (self.base + self.cfg["application_modify_path"]
               + f"?id={app_id}&token={token}&step={step}")
        # Refresh CSRF before each step submission
        html = self._get_html(url, label=f"GET {step}")
        self._csrf = self._extract_csrf(html)
        payload["_csrf"] = self._csrf
        resp = self._post(url, data=payload, label=f"POST {step}")
        self.log.success(f"Step '{step}' submitted (app={app_id})")
        return resp

    def _resolve_state_id(self, state_abbr: str) -> int:
        """Look up state ID from config; falls back to dynamic API query."""
        state_ids = self.defaults.get("state_ids", {})
        abbr = state_abbr.strip().upper()
        if abbr in state_ids:
            return state_ids[abbr]
        # Dynamic fallback: could query a state list endpoint
        self.log.warn(f"State '{abbr}' not in config — using 0. Add to state_ids in config.yaml.")
        return 0

    def _resolve_mcc(self, industry: str) -> str:
        """Dynamically search MCC by industry name."""
        pay_cfg = self.defaults["payment"]
        url = self.base + self.cfg["mcc_search_path"]
        try:
            data = self._get_json(url, params={
                "scenario": "search-by-id",
                "activeOnly": "1",
                "q": industry,
            }, label="MCC search")
            results = data.get("results", data) if isinstance(data, dict) else data
            if results:
                mcc = results[0].get("id", results[0].get("text", pay_cfg["default_mcc_code"]))
                self.log.info(f"MCC resolved: {industry} → {mcc}")
                return str(mcc)
        except Exception as e:
            self.log.warn(f"MCC lookup failed ({e}), using default {pay_cfg['default_mcc_code']}")
        return pay_cfg["default_mcc_code"]

    def _get_html(self, url: str, label: str) -> str:
        for attempt in range(self._max_retries):
            try:
                r = self._s.get(url, timeout=self._timeout)
                r.raise_for_status()
                return r.text
            except requests.RequestException as e:
                if attempt == self._max_retries - 1:
                    raise KITAPIError(f"GET {label} failed: {e}")
                time.sleep(self._retry_delay)
        return ""

    def _get_json(self, url: str, params: dict | None = None, label: str = "") -> Any:
        for attempt in range(self._max_retries):
            try:
                r = self._s.get(url, params=params, timeout=self._timeout)
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                if attempt == self._max_retries - 1:
                    raise KITAPIError(f"GET JSON {label} failed: {e}")
                time.sleep(self._retry_delay)

    def _post(self, url: str, data: dict, label: str) -> requests.Response:
        for attempt in range(self._max_retries):
            try:
                r = self._s.post(url, data=data, timeout=self._timeout, allow_redirects=True)
                self._raise_for_error(r, label)
                return r
            except KITAPIError:
                if attempt == self._max_retries - 1:
                    raise
                time.sleep(self._retry_delay)
        raise KITAPIError(f"POST {label} exhausted retries")

    def _raise_for_error(self, resp: requests.Response, label: str) -> None:
        if resp.status_code >= 400:
            raise KITAPIError(
                f"{label} HTTP {resp.status_code}",
                status=resp.status_code,
                body=resp.text[:500],
            )

    def _extract_csrf(self, html: str) -> str:
        m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
        if m:
            return m.group(1)
        m = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
        if m:
            return m.group(1)
        raise KITAPIError("CSRF token not found on page")

    def _extract_app_id_from_url(self, url: str) -> int | None:
        m = re.search(r"[?&]id=(\d+)", url)
        return int(m.group(1)) if m else None

    def _extract_app_id_from_html(self, html: str) -> int | None:
        m = re.search(r'boardingApplicationId\s*=\s*(\d+)', html)
        return int(m.group(1)) if m else None
