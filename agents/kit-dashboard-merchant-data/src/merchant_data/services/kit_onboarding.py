"""
KIT Dashboard Boarding Application API service.

Implements the full merchant onboarding flow via:
  POST /boarding-application          → create (gets app id)
  PUT  /boarding-application/{id}     → fill all fields
  GET  /boarding-application/{id}/validate → check errors
  GET  /boarding-application/mcc      → MCC lookup by code/description

Boarding process:
  1. create_application()  → returns OnboardingResult with app_id
  2. Caller calls validate_application(app_id) to check errors
  3. Caller can call get_application(app_id) to inspect full object

Base URL: https://dashboard.maverickpayments.com/api
Auth:     Bearer token (KIT_API_KEY in .env)
"""
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import Any

from merchant_data.models import (
    NewMerchantProfile,
    OnboardingAddress,
    OnboardingPrincipal,
    OnboardingResult,
    _STATE_NAME_TO_ID,
)

_BASE = "https://dashboard.maverickpayments.com/api"


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


class OnboardingAPIError(Exception):
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"API {status}: {body[:200]}")


class MerchantOnboardingService:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    # ── low-level HTTP ────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{_BASE}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "https://kitdashboard.com/",
                "Origin": "https://kitdashboard.com",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            },
        )
        try:
            with urllib.request.urlopen(req, context=_SSL) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            raise OnboardingAPIError(exc.code, raw) from exc

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _state_id(name: str) -> int:
        sid = _STATE_NAME_TO_ID.get(name)
        if sid is None:
            raise ValueError(
                f"Unknown state {name!r}. Use full name, e.g. 'California', 'Oklahoma'."
            )
        return sid

    @staticmethod
    def _addr_payload(addr: OnboardingAddress) -> dict:
        return {
            "street": addr.street,
            "city": addr.city,
            "zip": addr.zip,
            "state": {"id": MerchantOnboardingService._state_id(addr.state)},
            "country": {"id": addr.country_id},
        }

    @staticmethod
    def _principal_payload(p: OnboardingPrincipal, existing_id: int | None = None) -> dict:
        data: dict[str, Any] = {
            "title": p.title,
            "name": {"first": p.first_name, "last": p.last_name},
            "dayOfBirth": p.dob,
            "ssn": p.ssn,
            "phone": p.phone,
            "email": p.email,
            "ownershipPercentage": p.ownership_percentage,
            "isManagement": "Yes",
            "isSigner": "Yes",
            "isPersonalGuarantee": "Yes",
            "nationality": {"id": p.nationality_id},
            "address": MerchantOnboardingService._addr_payload(p.address),
        }
        if existing_id is not None:
            data["id"] = existing_id
        if p.dl_number:
            data["driverLicense"] = {
                "number": p.dl_number,
                "expiration": p.dl_expiration,
                "state": {"id": MerchantOnboardingService._state_id(p.dl_state)} if p.dl_state else {"id": None},
            }
        return data

    def _build_put_body(
        self, profile: NewMerchantProfile, existing_principal_ids: list[int]
    ) -> dict:
        addr = self._addr_payload(profile.business_address)
        # Auto-detect: if DBA name differs from legal name, mark sameAsCompany=No
        same = profile.dba_same_as_company and (profile.dba_name == profile.legal_name)
        dba_addr = addr  # address is always the same for now

        principals = []
        for i, p in enumerate(profile.principals):
            pid = existing_principal_ids[i] if i < len(existing_principal_ids) else None
            principals.append(self._principal_payload(p, pid))

        banks = []
        if profile.routing_number and profile.account_number:
            banks.append({
                "type": "All",
                "routingNumber": profile.routing_number,
                "accountNumber": profile.account_number,
            })

        return {
            "mcc": {"id": profile.mcc_id},
            "company": {
                "name": profile.legal_name,
                "type": profile.entity_type,
                "federalTaxId": profile.ein,
                "address": addr,
                "founded": profile.founded_date,
            },
            "dba": {
                "sameAsCompany": "Yes" if same else "No",
                "name": profile.dba_name,
                "address": dba_addr,
            },
            "serviceDescription": profile.service_description,
            "businessLocation": {
                "buildingType": "Office Building",
                "buildingOwnership": "Rents",
                "areaZoned": "Commercial",
                "squareFootage": "501-2500",
            },
            "customerServiceContact": {
                "phone": profile.business_phone,
                "email": profile.business_email,
            },
            "corporateContact": {
                "phone": profile.business_phone,
                "email": profile.business_email,
            },
            "bankruptcy": {"hasBankruptcy": "Never" if not profile.has_bankruptcy else "Yes"},
            "principals": principals,
            "processing": {
                "volumes": {
                    "monthlyTransactionAmount": profile.monthly_volume,
                    "avgTransactionAmount": profile.avg_transaction,
                    "maxTransactionAmount": profile.max_transaction,
                },
                "sales": {"swiped": 100, "mail": 0, "internet": 0},
                "alreadyProcessing": {"isProcessing": "Yes" if profile.already_processing else "No"},
                "terminated": {"isTerminated": "Yes" if profile.has_been_terminated else "No"},
                "intendedUsage": {
                    "creditCards": "Yes" if profile.accept_credit else "No",
                    "pinDebit": "Yes" if profile.accept_pin_debit else "No",
                    "ebt": "Yes" if profile.accept_ebt else "No",
                    "amex": {"optBlue": "Yes" if profile.accept_amex else "No"},
                },
                "recurringPayments": {"hasRecurring": "No"},
                "seasonalBusiness": {"isSeasonal": "Yes" if profile.is_seasonal else "No"},
                "inventory": {
                    "onSite": "Yes" if profile.inventory_on_site else "No",
                    "offSite": "No",
                    "thirdParty": "No",
                    "serviceOnly": "No",
                },
                "refundPolicy": profile.refund_policy,
                "equipmentUsed": "KIT POS",
                "banks": banks,
            },
        }

    # ── public API ────────────────────────────────────────────────────────────

    def create_application(self, profile: NewMerchantProfile) -> OnboardingResult:
        """Create and fill a boarding application in one call.

        Steps:
        1. POST /boarding-application → new app with id
        2. Extract auto-created principal id
        3. PUT /boarding-application/{id} → fill all data
        4. Validate and return result
        """
        # Step 1 – create skeleton
        created = self._request("POST", "/boarding-application", {
            "campaign": {"id": profile.campaign_id},
            "processingMethod": "Acquiring",
        })
        app_id: int = created["id"]

        # Step 2 – get auto-created principal IDs
        existing_ids = [p["id"] for p in created.get("principals", [])]

        # Step 3 – fill all fields (on failure, preserve app_id so caller can retry)
        put_body = self._build_put_body(profile, existing_ids)
        try:
            self._request("PUT", f"/boarding-application/{app_id}", put_body)
        except OnboardingAPIError as exc:
            raise OnboardingAPIError(exc.status, f"app_id={app_id} created but PUT failed: {exc.body}") from exc

        # Step 4 – validate
        errors = self.validate_application(app_id)
        status = "incomplete" if errors else "ready"

        return OnboardingResult(
            app_id=app_id,
            status=status,
            message=(
                "Application created. Validate errors must be resolved before submission."
                if errors
                else "Application created and fully populated."
            ),
            validation_errors=errors,
        )

    def update_application(self, app_id: int, profile: NewMerchantProfile) -> dict:
        """Re-fill an existing boarding application with updated profile data."""
        app = self._request("GET", f"/boarding-application/{app_id}")
        existing_ids = [p["id"] for p in app.get("principals", [])]
        put_body = self._build_put_body(profile, existing_ids)
        return self._request("PUT", f"/boarding-application/{app_id}", put_body)

    def get_application(self, app_id: int) -> dict:
        """Fetch the full boarding application object."""
        return self._request("GET", f"/boarding-application/{app_id}")

    def validate_application(self, app_id: int) -> dict[str, str]:
        """Return validation errors dict (empty dict = fully valid).

        API returns a dict of {field: message} on errors,
        or an empty list [] when all fields are valid.
        """
        try:
            result = self._request("GET", f"/boarding-application/{app_id}/validate")
            if isinstance(result, dict):
                return {k: v for k, v in result.items() if isinstance(v, str)}
            return {}  # empty list [] means valid
        except OnboardingAPIError:
            return {}

    def list_applications(
        self,
        limit: int = 20,
        status: str | None = None,
    ) -> list[dict]:
        """List boarding applications, newest first."""
        path = f"/boarding-application?per-page={min(limit, 50)}"
        if status:
            path += f"&filter[status]={urllib.parse.quote(status)}"
        result = self._request("GET", path)
        return result.get("items", [])

    def search_mcc(self, query: str) -> list[dict]:
        """Search MCCs by code number or description keyword.

        Returns list of {id, number, description} dicts.
        Use the id field when setting profile.mcc_id.
        """
        results = []
        page = 1
        while True:
            data = self._request("GET", f"/boarding-application/mcc?per-page=50&page={page}")
            items = data.get("items", [])
            if not items:
                break
            query_lower = query.lower()
            for item in items:
                if (
                    query_lower in item.get("number", "").lower()
                    or query_lower in item.get("description", "").lower()
                ):
                    results.append(item)
            meta = data.get("_meta", {})
            if page >= meta.get("pageCount", 1):
                break
            page += 1
        return results
