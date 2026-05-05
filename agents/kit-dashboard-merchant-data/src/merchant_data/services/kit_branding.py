"""
Merchant branding service — upload / remove logo for an active merchant.

The logo is tied to the DBA record. Upload goes through the KIT Dashboard
UI controller (not the REST API) and requires a session cookie.

Endpoints (all on kitdashboard.com, NOT dashboard.maverickpayments.com/api):
  POST /merchant/profile/upload-dba-logo?id=<dbaId>  — multipart/form-data, field: file
  GET  /merchant/profile/remove-dba-logo?id=<dbaId>  — remove logo
  GET  /merchant/public/dba-logo?id=<dbaId>           — fetch current logo bytes

dbaId ≠ merchantId.  dbaId = merchant.dbas[0].id from the REST API.
Session management is delegated to VarDownloader (shares the same cookie file).
"""
from __future__ import annotations

import json
import mimetypes
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from merchant_data.models import KitCredentials
from merchant_data.services.kit_var_downloader import VarDownloader

_KIT_BASE = "https://kitdashboard.com"
_API_BASE = "https://dashboard.maverickpayments.com/api"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/gif"}


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


@dataclass
class BrandingResult:
    merchant_name: str
    dba_id: int
    action: str  # "uploaded" | "removed"
    logo_path: Optional[Path] = None

    def summary(self) -> str:
        if self.action == "uploaded":
            return (
                f"✓ Logo uploaded for '{self.merchant_name}' "
                f"(dbaId={self.dba_id}, file={self.logo_path})"
            )
        return f"✓ Logo removed for '{self.merchant_name}' (dbaId={self.dba_id})"


class MerchantBrandingService:
    """Upload or remove the branding logo for an active (post-boarding) merchant.

    The logo is stored on the DBA record in KIT Dashboard.
    Session is shared with VarDownloader via the same cookie state file.
    """

    def __init__(self, api_key: str, credentials: KitCredentials) -> None:
        self.api_key = api_key
        # Session management (login, cookie jar) delegated to VarDownloader
        self._session = VarDownloader(api_key, credentials)

    # ------------------------------------------------------------------ public

    def upload_logo_by_internal_id(
        self, internal_id: int | str, image_path: Path
    ) -> BrandingResult:
        """Upload logo for the merchant identified by dashboard internal id."""
        item = self._api_get(f"/merchant/{internal_id}")
        merchant_name = item.get("name", str(internal_id))
        dba_id = self._get_dba_id(item, merchant_name)
        return self._upload(merchant_name, dba_id, image_path)

    def upload_logo_by_name(self, name: str, image_path: Path) -> BrandingResult:
        """Upload logo for the first merchant matching the given name."""
        data = self._api_get("/merchant", {"filter[name][like]": name, "per-page": 5})
        items = data.get("items", [])
        if not items:
            raise RuntimeError(f"No merchant found for name: {name!r}")
        item = items[0]
        merchant_name = item.get("name", name)
        dba_id = self._get_dba_id(item, merchant_name)
        return self._upload(merchant_name, dba_id, image_path)

    def upload_logo_by_mid(self, mid: str, image_path: Path) -> BrandingResult:
        """Upload logo for the merchant with the given 12-digit MID."""
        item = self._find_by_mid(mid)
        merchant_name = item.get("name", mid)
        dba_id = self._get_dba_id(item, merchant_name)
        return self._upload(merchant_name, dba_id, image_path)

    def remove_logo_by_internal_id(self, internal_id: int | str) -> BrandingResult:
        """Remove the logo for a merchant by dashboard internal id."""
        item = self._api_get(f"/merchant/{internal_id}")
        merchant_name = item.get("name", str(internal_id))
        dba_id = self._get_dba_id(item, merchant_name)
        return self._remove(merchant_name, dba_id)

    def remove_logo_by_name(self, name: str) -> BrandingResult:
        """Remove the logo for the first merchant matching the given name."""
        data = self._api_get("/merchant", {"filter[name][like]": name, "per-page": 5})
        items = data.get("items", [])
        if not items:
            raise RuntimeError(f"No merchant found for name: {name!r}")
        item = items[0]
        merchant_name = item.get("name", name)
        dba_id = self._get_dba_id(item, merchant_name)
        return self._remove(merchant_name, dba_id)

    # ------------------------------------------------------------ core actions

    def _upload(
        self, merchant_name: str, dba_id: int, image_path: Path
    ) -> BrandingResult:
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        file_bytes = image_path.read_bytes()
        mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
        if mime_type not in _ALLOWED_MIME:
            raise ValueError(
                f"Unsupported image type '{mime_type}'. Use JPEG, PNG, or GIF."
            )

        body, content_type = self._make_multipart(
            "file", image_path.name, file_bytes, mime_type
        )
        url = f"{_KIT_BASE}/merchant/profile/upload-dba-logo?id={dba_id}"

        cookie_str = self._get_valid_session()
        response = self._post_with_cookies(url, body, content_type, cookie_str)

        # If the response looks like a login redirect, re-authenticate and retry
        if self._looks_like_login_page(response):
            cookie_str = self._session._http_login()
            response = self._post_with_cookies(url, body, content_type, cookie_str)

        return BrandingResult(
            merchant_name=merchant_name,
            dba_id=dba_id,
            action="uploaded",
            logo_path=image_path,
        )

    def _remove(self, merchant_name: str, dba_id: int) -> BrandingResult:
        url = f"{_KIT_BASE}/merchant/profile/remove-dba-logo?id={dba_id}"
        cookie_str = self._get_valid_session()

        req = urllib.request.Request(
            url,
            headers={
                "Cookie": cookie_str,
                "User-Agent": _UA,
                "Referer": f"{_KIT_BASE}/merchant/profile/index",
                "Accept": "text/html,*/*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Remove logo failed: HTTP {exc.code}") from exc

        return BrandingResult(
            merchant_name=merchant_name,
            dba_id=dba_id,
            action="removed",
        )

    # ----------------------------------------------------------------- helpers

    def _get_valid_session(self) -> str:
        """Return a cookie string, logging in if no cached session exists."""
        cookie_str = self._session._load_session_cookies()
        if not cookie_str:
            cookie_str = self._session._http_login()
        return cookie_str

    def _post_with_cookies(
        self, url: str, body: bytes, content_type: str, cookie_str: str
    ) -> bytes:
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Cookie": cookie_str,
                "Content-Type": content_type,
                "User-Agent": _UA,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{_KIT_BASE}/merchant/profile/index",
                "Origin": _KIT_BASE,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Upload failed: HTTP {exc.code}: {err_body[:300]}"
            ) from exc

    @staticmethod
    def _make_multipart(
        field_name: str, filename: str, file_bytes: bytes, mime_type: str
    ) -> tuple[bytes, str]:
        """Build a multipart/form-data body for a single file field."""
        boundary = uuid.uuid4().hex
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n"
            "\r\n"
        ).encode()
        footer = f"\r\n--{boundary}--\r\n".encode()
        return header + file_bytes + footer, f"multipart/form-data; boundary={boundary}"

    @staticmethod
    def _looks_like_login_page(response: bytes) -> bool:
        snippet = response[:1000].lower()
        return b"log in" in snippet or b"/login" in snippet

    def _get_dba_id(self, item: dict, merchant_name: str) -> int:
        dbas = item.get("dbas", [])
        if not dbas:
            raise RuntimeError(f"Merchant '{merchant_name}' has no DBAs")
        dba_id = dbas[0].get("id")
        if not dba_id:
            raise RuntimeError(f"Could not get DBA ID for '{merchant_name}'")
        return int(dba_id)

    def _find_by_mid(self, mid: str) -> dict:
        mid_int = int(mid)
        page = 1
        while True:
            data = self._api_get("/merchant", {"per-page": 50, "page": page})
            for item in data.get("items", []):
                for dba in item.get("dbas", []):
                    if (dba.get("processing") or {}).get("mid") == mid_int:
                        return item
            meta = data.get("_meta", {})
            if page >= meta.get("pageCount", 1):
                break
            page += 1
        raise RuntimeError(f"No merchant found with MID: {mid}")

    def _api_get(self, path: str, params: dict | None = None) -> dict:
        qs = urllib.parse.urlencode(params or {})
        url = f"{_API_BASE}{path}{'?' + qs if qs else ''}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": _UA,
                "Referer": "https://kitdashboard.com/",
                "Origin": "https://kitdashboard.com",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            raise RuntimeError(f"API error {exc.code}: {body}") from exc
