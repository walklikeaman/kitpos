"""
VAR Sheet downloader — hybrid approach:

1. Maverick API  → merchant internal_id + terminal_id  (no browser)
2. Session cookie → Playwright login (once, then cached)
3. Direct HTTP    → download VAR PDF with session cookie (no browser navigation)

URL pattern: https://kitdashboard.com/merchant/profile/view-var-sheet
             ?id={internal_id}&terminalId={terminal_id}
"""
from __future__ import annotations

import json
import ssl
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
        headless: bool = True,
    ) -> None:
        self.api_key = api_key
        self.credentials = credentials
        self.headless = headless

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
        # Prefer active terminal; fallback to first
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

        # Step 1: Fetch profile page to get merchantAccountId and real VAR links
        var_url = self._get_var_url_from_profile(
            merchant_internal_id, terminal_id, cookie_str
        )

        # If we couldn't get a VAR URL (session expired) → re-login
        if var_url is None:
            cookie_str = self._browser_login_and_get_cookies()
            var_url = self._get_var_url_from_profile(
                merchant_internal_id, terminal_id, cookie_str
            )

        if var_url is None:
            raise RuntimeError(
                f"Could not find VAR link in profile for {merchant_name} "
                f"(id={merchant_internal_id}). Session may be invalid."
            )

        # Step 2: Download the PDF
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
        """Fetch merchant profile page, extract merchantAccountId and VAR links.

        The dashboard uses 'merchantAccountId' (≠ API merchant id) in VAR URLs.
        We parse all var-sheet links from the profile HTML and pick the one
        matching the preferred terminal (or just the first one).
        """
        if not cookie_str:
            return None
        profile_url = (
            f"{_KIT_BASE}/merchant/profile/index?id={merchant_internal_id}"
        )
        req = urllib.request.Request(profile_url, headers={
            "Cookie": cookie_str,
            "User-Agent": _UA,
            "Accept": "text/html,*/*",
            "Referer": f"{_KIT_BASE}/",
        })
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError:
            return None

        # If redirected to login page, session is invalid
        if "view-var-sheet" not in html:
            return None

        # Find all VAR sheet links, e.g.:
        # href="https://kitdashboard.com/merchant/profile/view-var-sheet?id=330902&terminalId=800750"
        import re
        var_links = re.findall(
            r'href="(https://kitdashboard\.com/merchant/profile/view-var-sheet\?[^"]+)"',
            html,
        )
        if not var_links:
            return None

        # Prefer the link matching the preferred terminal
        for link in var_links:
            if f"terminalId={preferred_terminal_id}" in link:
                return link.replace("&amp;", "&")

        # Fallback: first VAR link
        return var_links[0].replace("&amp;", "&")

    def _http_get_pdf(self, url: str, cookie_str: str) -> Optional[bytes]:
        """Download URL using session cookies. Returns bytes if PDF, None if got HTML."""
        req = urllib.request.Request(url, headers={
            "Cookie": cookie_str,
            "User-Agent": _UA,
            "Accept": "application/pdf,*/*",
            "Referer": f"{_KIT_BASE}/",
        })
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
                data = resp.read()
                if data[:4] == b"%PDF":
                    return data
                return None
        except urllib.error.HTTPError:
            return None

    # ---------------------------------------------------- session management

    def _load_session_cookies(self) -> str:
        """Load kitdashboard cookies from Playwright storage_state."""
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

    def _browser_login_and_get_cookies(self) -> str:
        """Fresh Playwright login, save state, return cookie string."""
        import asyncio
        return asyncio.run(self._async_login())

    async def _async_login(self) -> str:
        """Use the proven MerchantLookupService login, then return cookies."""
        from merchant_data.services.kit_merchant_lookup import MerchantLookupService

        svc = MerchantLookupService(self.credentials, headless=self.headless)

        from playwright.async_api import async_playwright
        creds = self.credentials
        creds.storage_state.parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            ctx_kwargs: dict = {"viewport": {"width": 1440, "height": 900}}
            if creds.storage_state.exists():
                ctx_kwargs["storage_state"] = str(creds.storage_state)
            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            page.set_default_timeout(20000)

            await svc._login(page)
            await ctx.storage_state(path=str(creds.storage_state))

            cookies = {
                c["name"]: c["value"]
                for c in (await ctx.cookies())
                if "kitdashboard" in c.get("domain", "")
            }
            await browser.close()

        return "; ".join(f"{k}={v}" for k, v in cookies.items())

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
