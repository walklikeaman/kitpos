"""
KIT Dashboard Boarding Application API service.

Implements the full merchant onboarding flow via:
  POST /boarding-application          → create (gets app id)
  PUT  /boarding-application/{id}     → fill all fields
  GET  /boarding-application/{id}/validate → check errors
  GET  /boarding-application/mcc      → MCC lookup by code/description
  POST /attachment/upload             → upload file, returns attachment id
  POST /boarding-application/{id}/document → link attachment to application
  DELETE /boarding-application/{id}/document/{attachment_id} → unlink document

Document upload flow:
  1. upload_attachment(path_or_bytes, filename) → attachment_id
  2. link_document(app_id, attachment_id, principal_id) → links to application
  3. list_documents(app_id) → returns current linked documents
  4. remove_document(app_id, attachment_id) → removes link

Boarding process:
  1. create_application()  → returns OnboardingResult with app_id
  2. Caller calls validate_application(app_id) to check errors
  3. Caller can call get_application(app_id) to inspect full object

Base URL: https://kitdashboard.com/api
Auth:     Bearer token (KIT_API_KEY in .env)
"""
from __future__ import annotations

import json
import mimetypes
import os
import ssl
import uuid
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Union

from merchant_data.models import (
    NewMerchantProfile,
    OnboardingAddress,
    OnboardingPrincipal,
    OnboardingResult,
    _STATE_NAME_TO_ID,
)

_BASE = "https://kitdashboard.com/api"

# Document type IDs (used in the `about` field of boarding application documents)
# Discovered by inspecting existing boarding applications via GET /boarding-application/{id}
DOCUMENT_TYPE_VOIDED_CHECK = 6
DOCUMENT_TYPE_DRIVER_LICENSE = 18
DOCUMENT_TYPE_OTHER = 3  # generic "Other" category


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

    @staticmethod
    def _build_multipart(
        fields: dict[str, str],
        file_field: str,
        filename: str,
        file_bytes: bytes,
        content_type: str,
    ) -> tuple[bytes, str]:
        """Build a multipart/form-data body. Returns (body_bytes, content_type_header)."""
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n".encode()
            )
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n".encode()
            + file_bytes
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        return b"".join(parts), f"multipart/form-data; boundary={boundary}"

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        raw_data: bytes | None = None,
        content_type: str = "application/json",
    ) -> Any:
        url = f"{_BASE}/{path.lstrip('/')}"
        if raw_data is not None:
            data = raw_data
        elif body is not None:
            data = json.dumps(body).encode()
            content_type = "application/json"
        else:
            data = None

        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Referer": "https://kitdashboard.com/",
            "Origin": "https://kitdashboard.com",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if data is not None:
            headers["Content-Type"] = content_type

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
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

        The API has a quirk: it returns 422 with body [] when all fields are
        valid (no errors), and 422 with a dict of {field: message} when there
        are validation errors.  We distinguish the two by inspecting the body.
        """
        try:
            result = self._request("GET", f"/boarding-application/{app_id}/validate")
            if isinstance(result, dict):
                return {k: v for k, v in result.items() if isinstance(v, str)}
            return {}  # empty list [] means valid
        except OnboardingAPIError as exc:
            # 422 with body "[]" → fully valid (API quirk)
            try:
                body = json.loads(exc.body)
                if isinstance(body, list) and len(body) == 0:
                    return {}
                if isinstance(body, dict):
                    return {k: v for k, v in body.items() if isinstance(v, str)}
            except (json.JSONDecodeError, AttributeError):
                pass
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

    # ── document upload ───────────────────────────────────────────────────────

    def upload_attachment(
        self,
        source: Union[str, Path, bytes],
        filename: str | None = None,
    ) -> int:
        """Upload a file to the KIT attachment store.

        Args:
            source: File path (str/Path) or raw bytes.
            filename: Override filename. Defaults to basename of path or 'file'.

        Returns:
            attachment_id (int) — use this with link_document().
        """
        if isinstance(source, (str, Path)):
            path = Path(source)
            file_bytes = path.read_bytes()
            if filename is None:
                filename = path.name
        else:
            file_bytes = source
            if filename is None:
                filename = "file"

        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body, ct_header = self._build_multipart(
            fields={},
            file_field="file",
            filename=filename,
            file_bytes=file_bytes,
            content_type=mime,
        )
        result = self._request("POST", "/attachment/upload", raw_data=body, content_type=ct_header)
        return result["id"]

    def link_document(
        self,
        app_id: int,
        attachment_id: int,
        principal_id: int | None = None,
        doc_type_id: int | None = None,
    ) -> dict:
        """Link an uploaded attachment to a boarding application.

        Args:
            app_id: Boarding application ID.
            attachment_id: ID returned by upload_attachment().
            principal_id: Optional principal to associate the document with.
            doc_type_id: Document type integer ID. Use module constants:
                DOCUMENT_TYPE_VOIDED_CHECK = 6
                DOCUMENT_TYPE_DRIVER_LICENSE = 18
                DOCUMENT_TYPE_OTHER = 3

        Returns:
            The document link object from the API.

        Note:
            To update the type on an already-linked document, call
            set_document_type(app_id, attachment_id, doc_type_id).
        """
        payload: dict[str, Any] = {"attachment": {"id": attachment_id}}
        if principal_id is not None:
            payload["principal"] = {"id": principal_id}
        if doc_type_id is not None:
            payload["about"] = [doc_type_id]
        return self._request("POST", f"/boarding-application/{app_id}/document", body=payload)

    def set_document_type(
        self,
        app_id: int,
        attachment_id: int,
        doc_type_id: int,
        principal_id: int | None = None,
    ) -> dict:
        """Set or update the document type for an already-linked document.

        The `about` field uses integer IDs (not strings):
            DOCUMENT_TYPE_VOIDED_CHECK   = 6
            DOCUMENT_TYPE_DRIVER_LICENSE = 18
            DOCUMENT_TYPE_OTHER          = 3

        Args:
            app_id: Boarding application ID.
            attachment_id: Attachment ID of the already-linked document.
            doc_type_id: Integer document type ID.
            principal_id: Principal to associate (preserves existing if None).

        Returns:
            Updated document object from the API.
        """
        payload: dict[str, Any] = {
            "attachment": {"id": attachment_id},
            "about": [doc_type_id],
        }
        if principal_id is not None:
            payload["principal"] = {"id": principal_id}
        return self._request(
            "PUT", f"/boarding-application/{app_id}/document/{attachment_id}", body=payload
        )

    def remove_document(self, app_id: int, attachment_id: int) -> bool:
        """Remove a document link from a boarding application.

        Args:
            app_id: Boarding application ID.
            attachment_id: Attachment ID to unlink.

        Returns:
            True if successfully removed.
        """
        try:
            result = self._request("DELETE", f"/boarding-application/{app_id}/document/{attachment_id}")
            return bool(result)
        except OnboardingAPIError:
            return False

    def list_documents(self, app_id: int) -> list[dict]:
        """Return all documents currently linked to a boarding application."""
        app = self._request("GET", f"/boarding-application/{app_id}")
        return app.get("documents", [])

    def upload_and_link_document(
        self,
        app_id: int,
        source: Union[str, Path, bytes],
        filename: str | None = None,
        principal_id: int | None = None,
        doc_type_id: int | None = None,
    ) -> int:
        """Upload a file and immediately link it to a boarding application.

        Convenience wrapper around upload_attachment() + link_document().

        Args:
            app_id: Boarding application ID.
            source: File path or raw bytes.
            filename: Override filename.
            principal_id: Principal to associate with.
            doc_type_id: Document type integer ID. Use module constants:
                DOCUMENT_TYPE_VOIDED_CHECK   = 6
                DOCUMENT_TYPE_DRIVER_LICENSE = 18
                DOCUMENT_TYPE_OTHER          = 3

        Returns:
            attachment_id of the newly uploaded and linked document.
        """
        attachment_id = self.upload_attachment(source, filename)
        self.link_document(app_id, attachment_id, principal_id, doc_type_id)
        return attachment_id

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
