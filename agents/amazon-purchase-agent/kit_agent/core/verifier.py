"""
Application verifier — checks each section of a KIT Dashboard application for
empty required fields, validation errors, and missing documents.

Strategy (learned from production HTML inspection):
  - All form fields live in the 'business' step HTML — including principal fields
  - Banking fields (routing/account) live under a 0-bankroutingnumber / 0-bankaccountnumber ID pattern
  - Payment fields (volume, mcc, etc.) live in the 'acquiring' step HTML
  - Documents are NOT in the HTML — must be fetched from /boarding/attachment/list API
  - Select2 dropdowns use <option value="X" selected> (value BEFORE 'selected' keyword)
"""
from __future__ import annotations
import re
from typing import Any

from .logger import SessionLogger


def _get_val(html: str, field_id: str) -> str | None:
    """Extract value of an input, select, or textarea by element id."""
    fid = re.escape(field_id)
    # input / hidden: id="..." value="..."
    m = re.search(rf'id="{fid}"[^>]*value="([^"]*)"', html, re.I)
    if m:
        return m.group(1)
    # select: id="..." ... <option value="X" selected ...>
    sb = re.search(rf'id="{fid}"(.*?)</select>', html, re.I | re.DOTALL)
    if sb:
        sm = re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', sb.group(1), re.I)
        if sm:
            return sm.group(1)
    # textarea: id="...">content</textarea>
    ta = re.search(rf'id="{fid}"[^>]*>(.*?)</textarea>', html, re.I | re.DOTALL)
    if ta:
        return ta.group(1).strip()
    return None


# Fields to check and their human-readable labels
# (field_id, display_label)
BUSINESS_FIELDS = [
    ("boardingapplicationmodifyform-companyname",     "Legal Name"),
    ("boardingapplicationmodifyform-businesstype",    "Entity Type"),
    ("boardingapplicationmodifyform-companyaddress",  "Business Street"),
    ("boardingapplicationmodifyform-companyzip",      "Business ZIP"),
    ("boardingapplicationmodifyform-companycity",     "Business City"),
    ("boardingapplicationmodifyform-company_state_id","Business State"),
    ("boardingapplicationmodifyform-foundeddate",     "Founded Date"),
    ("boardingapplicationmodifyform-federaltaxid",    "EIN"),
    ("boardingapplicationmodifyform-dbaname",         "DBA Name"),
]

PRINCIPAL_FIELDS = [
    ("boardingapplicationbusinessownermodifyform-0-firstname",         "First Name"),
    ("boardingapplicationbusinessownermodifyform-0-lastname",          "Last Name"),
    ("boardingapplicationbusinessownermodifyform-0-ssn",               "SSN"),
    ("boardingapplicationbusinessownermodifyform-0-dayofbirthformatted","Date of Birth"),
    ("boardingapplicationbusinessownermodifyform-0-driverlicensenum",  "Driver License #"),
    ("boardingapplicationbusinessownermodifyform-0-driverlicensestate_id","DL State"),
    ("boardingapplicationbusinessownermodifyform-0-address",           "Home Street"),
    ("boardingapplicationbusinessownermodifyform-0-zip",               "Home ZIP"),
    ("boardingapplicationbusinessownermodifyform-0-city",              "Home City"),
    ("boardingapplicationbusinessownermodifyform-0-state_id",          "Home State"),
    ("boardingapplicationbusinessownermodifyform-0-phone",             "Phone"),
    ("boardingapplicationbusinessownermodifyform-0-ownershippercentage","Ownership %"),
]

BANKING_FIELDS = [
    ("boardingapplicationacquiringbankaccountmodifyform-0-bankroutingnumber", "Routing Number"),
    ("boardingapplicationacquiringbankaccountmodifyform-0-bankaccountnumber", "Account Number"),
]

PAYMENT_FIELDS = [
    ("boardingapplicationacquiringmodifyform-monthlytransactionamount", "Monthly Volume"),
    ("boardingapplicationacquiringmodifyform-avgtransactionamount",     "Average Ticket"),
    ("boardingapplicationacquiringmodifyform-maxtransactionamount",     "Max Ticket"),
    ("boardingapplicationacquiringmodifyform-refundpolicy",             "Refund Policy"),
    ("boardingapplicationmodifyform-mcc_id",                            "MCC / Industry"),
]

# Document categories that must be present
REQUIRED_DOC_CATEGORIES = {
    "voided-check": "Voided Check",
    "driver-license": "Driver License",
}


class ApplicationVerifier:
    def __init__(self, api_client, log: SessionLogger):
        self.client = api_client
        self.log = log

    def verify_all_steps(self, app_id: int, token: str) -> dict[str, Any]:
        """
        Verify all sections of the application.
        Returns {section: {"status": "ok|warn|error", "empty": [...], "invalid": [...]}}
        """
        self.log.step("Verify application completeness")
        base = self.client.base
        cfg = self.client.cfg
        mod_path = cfg["application_modify_path"]

        results: dict[str, Any] = {}

        # ── Business + Principal (both on 'business' step HTML) ──────────
        try:
            url = f"{base}{mod_path}?id={app_id}&token={token}&step=business"
            html = self.client._get_html(url, "verify business")
            biz_r = self._check_fields(html, BUSINESS_FIELDS, "business")
            pri_r = self._check_fields(html, PRINCIPAL_FIELDS, "principal")
            results["business"] = biz_r
            results["principal"] = pri_r
        except Exception as e:
            results["business"] = _err(e)
            results["principal"] = _err(e)
            self.log.warn(f"Could not verify business/principal: {e}")

        # ── Banking (processing step) ────────────────────────────────────
        try:
            url = f"{base}{mod_path}?id={app_id}&token={token}&step=processing"
            html = self.client._get_html(url, "verify processing")
            results["processing"] = self._check_fields(html, BANKING_FIELDS, "processing")
        except Exception as e:
            results["processing"] = _err(e)
            self.log.warn(f"Could not verify processing: {e}")

        # ── Payment / Acquiring ──────────────────────────────────────────
        try:
            url = f"{base}{mod_path}?id={app_id}&token={token}&step=acquiring"
            html = self.client._get_html(url, "verify acquiring")
            results["acquiring"] = self._check_fields(html, PAYMENT_FIELDS, "acquiring")
        except Exception as e:
            results["acquiring"] = _err(e)
            self.log.warn(f"Could not verify acquiring: {e}")

        # ── Documents (via attachment list API) ──────────────────────────
        try:
            att_url = f"{base}/boarding/attachment/list?id={app_id}&token={token}"
            att_resp = self.client._s.get(att_url, timeout=self.client._timeout)
            att_data = att_resp.json()
            items = att_data.get("items", []) if isinstance(att_data, dict) else att_data
            found_cats: set[str] = set()
            for item in items:
                att = item.get("attachment", item)
                for key in att.get("aboutKeys", []):
                    found_cats.add(key)
            missing = [REQUIRED_DOC_CATEGORIES[c] for c in REQUIRED_DOC_CATEGORIES if c not in found_cats]
            results["documents"] = {
                "status": "ok" if not missing else "error",
                "empty": missing,
                "invalid": [],
                "found": list(found_cats),
            }
            self.log.info(f"Documents: found={list(found_cats)}, missing={missing}")
        except Exception as e:
            results["documents"] = _err(e)
            self.log.warn(f"Could not verify documents: {e}")

        # Log summary
        for section, r in results.items():
            icon = "✅" if r["status"] == "ok" else ("⚠️" if r["status"] == "warn" else "❌")
            self.log.info(
                f"{icon} {section}: {len(r['empty'])} empty, {len(r['invalid'])} invalid"
            )

        return results

    def _check_fields(self, html: str, fields: list, section: str) -> dict:
        empty = []
        for field_id, label in fields:
            val = _get_val(html, field_id)
            if val is None or val.strip() in ("", "0"):
                empty.append(label)

        # Check for is-invalid red-bordered inputs
        invalid_ids = re.findall(
            r'<(?:input|select|textarea)[^>]*id="([^"]+)"[^>]*class="[^"]*is-invalid[^"]*"',
            html, re.I
        )
        invalid_ids += re.findall(
            r'<(?:input|select|textarea)[^>]*class="[^"]*is-invalid[^"]*"[^>]*id="([^"]+)"',
            html, re.I
        )
        # Map IDs to human labels for known fields
        all_labels = {fid: lbl for fid, lbl in BUSINESS_FIELDS + PRINCIPAL_FIELDS + BANKING_FIELDS + PAYMENT_FIELDS}
        invalid = [all_labels.get(i.lower(), i) for i in set(invalid_ids)]

        status = "ok"
        if invalid:
            status = "error"
        elif empty:
            status = "warn"
        return {"status": status, "empty": empty, "invalid": invalid}


def _err(e: Exception) -> dict:
    return {"status": "error", "empty": [], "invalid": [], "error": str(e)}
