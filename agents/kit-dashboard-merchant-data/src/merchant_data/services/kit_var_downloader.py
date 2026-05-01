"""
VAR Sheet downloader — fully browserless approach:

1. Maverick API      → merchant internal_id + terminal_id
2. HTTP login        → POST credentials to /login, handle 2FA, get msession cookie
3. Profile page HTTP → parse merchantAccountId from HTML (used in VAR URL)
4. Direct HTTP       → download VAR PDF with session cookie

No Playwright / no browser required at any step.

URL pattern: https://kitdashboard.com/merchant/profile/view-var-sheet
             ?id={merchant_account_id}&terminalId={terminal_id}

Note: merchant_account_id ≠ API merchant.id — it's the "acquiring account" ID
      that only appears in the dashboard profile page HTML.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from merchant_data.models import KitCredentials, VarDownloadResult

_KIT_BASE = "https://kitdashboard.com"
_API_BASE = "https://dashboard.maverickpayments.com/api"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
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


class VarDownloader:
    def __init__(
        self,
        api_key: str,
        credentials: KitCredentials,
        *,
        headless: bool = True,  # kept for CLI compatibility, no longer used
    ) -> None:
        self.api_key = api_key
        self.credentials = credentials

    # ------------------------------------------------------------------ public

    def download_by_mid(self, mid: str, save_dir: Path) -> VarDownloadResult:
        """Find merchant by MID, get first terminal, download VAR PDF."""
        merchant_id, merchant_name, terminal_id = self._resolve_by_mid(mid)
        return self._download(merchant_id, merchant_name, mid, terminal_id, save_dir)

    def download_by_name(self, name: str, save_dir: Path) -> VarDownloadResult:
        """Find merchant by name, get first terminal, download VAR PDF."""
        merchant_id, merchant_name, mid, terminal_id = self._resolve_by_name(name)
        return self._download(merchant_id, merchant_name, mid, terminal_id, save_dir)

    # ---------------------------------------------------- API resolution layer

    def _resolve_by_name(self, name: str) -> tuple[int, str, str, int]:
        """Return (internal_id, merchant_name, mid, terminal_id)."""
        params = {"filter[name][like]": name, "per-page": 5}
        data = self._api_get("/merchant", params)
        items = data.get("items", [])
        if not items:
            raise RuntimeError(f"No merchant found for name: {name!r}")
        item = items[0]
        internal_id = item["id"]
        merchant_name = item["name"]
        dba = (item.get("dbas") or [{}])[0]
        proc = dba.get("processing") or {}
        mid = str(proc.get("mid", ""))
        terminal_id = self._get_first_terminal_id(internal_id)
        return internal_id, merchant_name, mid, terminal_id

    def _resolve_by_mid(self, mid: str) -> tuple[int, str, int]:
        """Return (internal_id, merchant_name, terminal_id) by scanning all merchants."""
        mid_int = int(mid)
        page = 1
        while True:
            data = self._api_get("/merchant", {"per-page": 50, "page": page})
            for item in data.get("items", []):
                for dba in item.get("dbas", []):
                    proc = dba.get("processing") or {}
                    if proc.get("mid") == mid_int:
                        internal_id = item["id"]
                        terminal_id = self._get_first_terminal_id(internal_id)
                        return internal_id, item["name"], terminal_id
            meta = data.get("_meta", {})
            if page >= meta.get("pageCount", 1):
                break
            page += 1
        raise RuntimeError(f"No merchant found with MID: {mid}")

    def _get_first_terminal_id(self, merchant_internal_id: int) -> int:
        """Get the first active terminal ID for the merchant via API."""
        data = self._api_get(
            "/terminal",
            {"filter[merchant.id][eq]": merchant_internal_id, "per-page": 10},
        )
        items = data.get("items", [])
        if not items:
            raise RuntimeError(
                f"No terminals found for merchant id={merchant_internal_id}"
            )
        active = [t for t in items if t.get("status", "").lower() == "active"]
        chosen = active[0] if active else items[0]
        return int(chosen["id"])

    # ------------------------------------------------------- download core

    def _download(
        self,
        merchant_internal_id: int,
        merchant_name: str,
        mid: str,
        terminal_id: int,
        save_dir: Path,
    ) -> VarDownloadResult:
        save_dir.mkdir(parents=True, exist_ok=True)
        profile_url = f"{_KIT_BASE}/merchant/profile/index?id={merchant_internal_id}"

        # Try with cached session first
        cookie_str = self._load_session_cookies()

        # Fetch profile page to get VAR links (contains merchantAccountId)
        var_url = self._get_var_url_from_profile(
            merchant_internal_id, terminal_id, cookie_str
        )

        # Session expired → HTTP login and retry
        if var_url is None:
            cookie_str = self._http_login()
            var_url = self._get_var_url_from_profile(
                merchant_internal_id, terminal_id, cookie_str
            )

        if var_url is None:
            raise RuntimeError(
                f"Could not find VAR link in profile for {merchant_name} "
                f"(id={merchant_internal_id}). Login may have failed."
            )

        pdf_bytes = self._http_get_pdf(var_url, cookie_str)
        if pdf_bytes is None:
            raise RuntimeError(
                f"Failed to download VAR PDF for merchant {merchant_name} "
                f"(url={var_url}). Got HTML instead of PDF."
            )

        filename = f"{merchant_name.replace(' ', '-')}-VAR-Sheet.pdf"
        dest = save_dir / filename
        dest.write_bytes(pdf_bytes)
        return VarDownloadResult(
            merchant_name=merchant_name,
            search_term=mid or str(merchant_internal_id),
            profile_url=profile_url,
            saved_path=dest,
        )

    def _get_var_url_from_profile(
        self,
        merchant_internal_id: int,
        preferred_terminal_id: int,
        cookie_str: str,
    ) -> Optional[str]:
        """Fetch merchant profile page, parse VAR links from HTML.

        The dashboard uses 'merchantAccountId' (≠ API merchant.id) in VAR URLs.
        e.g. /view-var-sheet?id=330902&terminalId=800750
             where 330902 is merchantAccountId, 299390 is API merchant.id
        """
        if not cookie_str:
            return None
        req = urllib.request.Request(
            f"{_KIT_BASE}/merchant/profile/index?id={merchant_internal_id}",
            headers={
                "Cookie": cookie_str,
                "User-Agent": _UA,
                "Accept": "text/html,*/*",
                "Referer": f"{_KIT_BASE}/",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError:
            return None

        if "view-var-sheet" not in html:
            return None  # session invalid or merchant has no VAR

        var_links = re.findall(
            r'href="(https://kitdashboard\.com/merchant/profile/view-var-sheet\?[^"]+)"',
            html,
        )
        if not var_links:
            return None

        for link in var_links:
            if f"terminalId={preferred_terminal_id}" in link:
                return link.replace("&amp;", "&")

        return var_links[0].replace("&amp;", "&")

    def _http_get_pdf(self, url: str, cookie_str: str) -> Optional[bytes]:
        """Download URL using session cookies. Returns bytes if PDF, else None."""
        req = urllib.request.Request(url, headers={
            "Cookie": cookie_str,
            "User-Agent": _UA,
            "Accept": "application/pdf,*/*",
            "Referer": f"{_KIT_BASE}/",
        })
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
                data = resp.read()
                return data if data[:4] == b"%PDF" else None
        except urllib.error.HTTPError:
            return None

    # ---------------------------------------------------- session management

    def _load_session_cookies(self) -> str:
        """Load kitdashboard cookies from saved JSON state."""
        state_path = self.credentials.storage_state
        if not state_path.exists():
            return ""
        try:
            state = json.loads(state_path.read_text())
            cookies = {
                c["name"]: c["value"]
                for c in state.get("cookies", [])
                if "kitdashboard" in c.get("domain", "")
            }
            return "; ".join(f"{k}={v}" for k, v in cookies.items())
        except Exception:
            return ""

    def _preload_cookies_into_jar(self, jar: http.cookiejar.CookieJar) -> None:
        """Inject saved cookies (deviceId, tsv_*, msession, …) into the jar.

        This makes the server treat the HTTP client as a trusted device,
        skipping 2FA on re-login even after the msession expires.
        """
        state_path = self.credentials.storage_state
        if not state_path.exists():
            return
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            return
        for c in state.get("cookies", []):
            if "kitdashboard" not in c.get("domain", ""):
                continue
            cookie = http.cookiejar.Cookie(
                version=0,
                name=c["name"],
                value=c["value"],
                port=None,
                port_specified=False,
                domain=c.get("domain", "kitdashboard.com"),
                domain_specified=True,
                domain_initial_dot=c.get("domain", "").startswith("."),
                path=c.get("path", "/"),
                path_specified=True,
                secure=c.get("secure", False),
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
            )
            jar.set_cookie(cookie)

    def _save_session_cookies(self, jar: http.cookiejar.CookieJar) -> str:
        """Persist cookies from a CookieJar to JSON and return cookie string."""
        creds = self.credentials
        creds.storage_state.parent.mkdir(parents=True, exist_ok=True)

        kit_cookies = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain or "kitdashboard.com",
                "path": c.path or "/",
                "secure": bool(c.secure),
                "httpOnly": False,
                "sameSite": "Lax",
            }
            for c in jar
            if "kitdashboard" in (c.domain or "")
        ]
        state = {"cookies": kit_cookies, "origins": []}
        creds.storage_state.write_text(json.dumps(state, indent=2))

        return "; ".join(f"{c['name']}={c['value']}" for c in kit_cookies)

    def _http_login(self) -> str:
        """Log in to kitdashboard via pure HTTP (no browser).

        Flow:
          1. Pre-load saved cookies (deviceId + tsv_* trust token) into jar
          2. GET /login  → CSRF token + fresh session cookie
          3. POST creds  → dashboard (success, no 2FA) or 2FA form
          4. If 2FA:     → wait for code, POST again with verificationCode
          5. Save all cookies to storage_state JSON
        """
        creds = self.credentials
        jar = http.cookiejar.CookieJar()

        # Pre-load existing cookies so the server recognises the trusted device.
        # The tsv_* and deviceId cookies tell the server to skip 2FA.
        self._preload_cookies_into_jar(jar)

        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_SSL),
            urllib.request.HTTPCookieProcessor(jar),
        )

        _hdrs = {
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": _KIT_BASE,
        }

        # ── Step 1: GET login page ────────────────────────────────────────────
        resp = opener.open(
            urllib.request.Request(f"{_KIT_BASE}/", headers=_hdrs), timeout=15
        )
        html = resp.read().decode("utf-8", errors="replace")
        csrf_m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
        if not csrf_m:
            raise RuntimeError("Could not find CSRF token on login page")
        csrf = csrf_m.group(1)

        # ── Step 2: POST credentials ─────────────────────────────────────────
        data = urllib.parse.urlencode({
            "_csrf": csrf,
            "LoginForm[username]": creds.email,
            "LoginForm[password]": creds.password,
            "LoginForm[rememberMe]": "1",
            "LoginForm[twoStepVerificationId]": "",
        }).encode()
        resp2 = opener.open(
            urllib.request.Request(
                f"{_KIT_BASE}/login",
                data=data,
                headers={**_hdrs,
                          "Content-Type": "application/x-www-form-urlencoded",
                          "Referer": f"{_KIT_BASE}/login"},
            ),
            timeout=15,
        )
        html2 = resp2.read().decode("utf-8", errors="replace")

        # Check if logged in already (no 2FA)
        if "verificationCode" not in html2:
            return self._save_session_cookies(jar)

        # ── Step 3: 2FA required ─────────────────────────────────────────────
        vid_m = re.search(
            r'name="LoginForm\[twoStepVerificationId\]"\s+value="([^"]+)"', html2
        )
        csrf2_m = re.search(r'name="_csrf"\s+value="([^"]+)"', html2)
        if not vid_m or not csrf2_m:
            raise RuntimeError("Could not parse 2FA form fields")
        verification_id = vid_m.group(1)
        csrf2 = csrf2_m.group(1)

        code = self._get_2fa_code()

        data3 = urllib.parse.urlencode({
            "_csrf": csrf2,
            "LoginForm[username]": creds.email,
            "LoginForm[password]": creds.password,
            "LoginForm[rememberMe]": "1",
            "LoginForm[twoStepVerificationId]": verification_id,
            "LoginForm[verificationCode]": code,
        }).encode()
        opener.open(
            urllib.request.Request(
                f"{_KIT_BASE}/login",
                data=data3,
                headers={**_hdrs,
                          "Content-Type": "application/x-www-form-urlencoded",
                          "Referer": f"{_KIT_BASE}/login"},
            ),
            timeout=15,
        )

        return self._save_session_cookies(jar)

    def _get_2fa_code(self) -> str:
        """Return 2FA code from credentials or wait for it via file bridge."""
        if self.credentials.verification_code:
            return self.credentials.verification_code

        # File bridge: write trigger, poll for code
        tmp = self.credentials.storage_state.parent
        trigger = tmp / "2fa_requested.txt"
        code_file = tmp / "2fa_code.txt"
        code_file.unlink(missing_ok=True)
        trigger.write_text(str(int(time.time())))
        print("[2FA] Waiting for 2FA code (reading from Gmail automatically)...")

        deadline = time.time() + 90
        while time.time() < deadline:
            if code_file.exists():
                code = code_file.read_text().strip()
                code_file.unlink(missing_ok=True)
                trigger.unlink(missing_ok=True)
                print(f"[2FA] Code received: {code}")
                return code
            time.sleep(2)

        raise RuntimeError(
            "2FA timeout: no code received within 90 s. "
            f"Write code to {code_file} or pass --verification-code."
        )

    # ----------------------------------------------------------- API helper

    def _api_get(self, path: str, params: dict) -> dict:
        qs = urllib.parse.urlencode(params)
        url = f"{_API_BASE}{path}{'?' + qs if qs else ''}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": _UA,
            "Referer": "https://kitdashboard.com/",
            "Origin": "https://kitdashboard.com",
        })
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            raise RuntimeError(f"API error {exc.code}: {body}") from exc
