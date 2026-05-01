"""
KIT Dashboard Merchant API service.

Uses the Maverick Payments REST API instead of a headless browser.
Base URL: https://dashboard.maverickpayments.com/api
Auth:     Bearer token (KIT_API_KEY in .env)

Filterable fields on /api/merchant:
  - id         (internal API id, same as ?id= in profile URL)
  - name       (DBA/legal name, supports [like])
  - NOTE: filter[dbas.processing.mid] is listed in docs but returns 422 —
    workaround: paginate all merchants and scan locally for matching MID.
"""
from __future__ import annotations

import ssl
import urllib.parse
import urllib.request
import json
from pathlib import Path

# macOS ships with outdated root certs; create a verified context via certifi or
# fall back to the system context without verification for internal dashboards.
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

from merchant_data.models import MerchantResult

_BASE = "https://dashboard.maverickpayments.com/api"
_PER_PAGE = 50  # API maximum


class MerchantAPIService:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    # ------------------------------------------------------------------ public

    def lookup_by_name(self, name: str) -> MerchantResult:
        """One API call — search by partial merchant name."""
        params = {"filter[name][like]": name, "per-page": _PER_PAGE}
        data = self._get("/merchant", params)
        items = data.get("items", [])
        if not items:
            raise RuntimeError(f"No merchants found for name: {name!r}")
        return self._parse(items[0])

    def lookup_by_mid(self, mid: str) -> MerchantResult:
        """
        Search by KIT Merchant ID (12-digit MID like 201100300996).
        API filter for mid is broken (returns 422), so we paginate all
        merchants and scan for a matching MID value in dbas.processing.mid.
        627 total merchants → 13 pages of 50 → fast.
        """
        mid_int = int(mid)
        page = 1
        while True:
            data = self._get("/merchant", {"per-page": _PER_PAGE, "page": page})
            for item in data.get("items", []):
                for dba in item.get("dbas", []):
                    proc = dba.get("processing") or {}
                    if proc.get("mid") == mid_int:
                        return self._parse(item)
            meta = data.get("_meta", {})
            if page >= meta.get("pageCount", 1):
                break
            page += 1
        raise RuntimeError(f"No merchant found with MID: {mid}")

    def lookup_by_internal_id(self, internal_id: int | str) -> MerchantResult:
        """Direct lookup by internal API id (same as ?id= in profile URL)."""
        data = self._get(f"/merchant/{internal_id}", {})
        return self._parse(data)

    # --------------------------------------------------------------- internals

    def _get(self, path: str, params: dict) -> dict:
        qs = urllib.parse.urlencode(params)
        url = f"{_BASE}{path}{'?' + qs if qs else ''}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://kitdashboard.com/",
            "Origin": "https://kitdashboard.com",
        })
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            raise RuntimeError(f"API error {exc.code}: {body}") from exc

    @staticmethod
    def _parse(item: dict) -> MerchantResult:
        merchant_name = item.get("name", "")
        internal_id = item.get("id", "")
        profile_url = (
            f"https://kitdashboard.com/merchant/profile/index?id={internal_id}"
        )

        # Principal: first signer or first principal
        principals = item.get("principals", [])
        principal = next(
            (p for p in principals if p.get("isSigner") == "Yes"),
            principals[0] if principals else {},
        )
        pname = principal.get("name", {})
        principal_name = f"{pname.get('first', '').strip()} {pname.get('last', '').strip()}".strip()

        # DBA details (first DBA)
        dbas = item.get("dbas", [])
        dba = dbas[0] if dbas else {}
        contact = dba.get("customerServiceContact", {})
        phone = contact.get("phone", "")
        email = contact.get("email", "")

        # MID
        proc = dba.get("processing", {})
        mid = str(proc.get("mid", ""))

        # Business address
        addr = dba.get("address", {})
        address_parts = [
            addr.get("street", ""),
            addr.get("city", ""),
            addr.get("zip", ""),
        ]
        business_address = ", ".join(p for p in address_parts if p)

        return MerchantResult(
            merchant_id=mid,
            merchant_name=merchant_name,
            profile_url=profile_url,
            principal_name=principal_name,
            phone=phone,
            email=email,
            business_address=business_address,
            raw_fields={},
        )
