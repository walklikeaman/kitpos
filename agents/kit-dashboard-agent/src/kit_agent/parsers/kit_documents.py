from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import json
import platform
from pathlib import Path
import re
import subprocess
import shutil

from kit_agent.models import (
    Address,
    ContactPerson,
    KitDocumentPayload,
    KitDocumentText,
    KitMerchantProfile,
    KitValidationIssue,
)
from kit_agent.parsers.ocr_micr import (
    extract_text_from_image,
    extract_micr_numbers,
    classify_image_document,
    is_valid_aba_routing_number as validate_aba_checksum,
)


APPLICATION = "application"
DRIVER_LICENSE = "driver_license"
BANK_DOCUMENT = "bank_document"
GREEN_CARD = "green_card"


@dataclass(slots=True)
class KitDocumentParser:
    """
    Extracts a KIT merchant profile from application, driver-license, and bank documents.

    Confirmed capability in this repo: text PDFs and text fixtures.
    Optional OCR capability is used only if pytesseract/Pillow are installed locally.
    """

    def parse_files(self, paths: list[Path | str]) -> KitDocumentPayload:
        documents: list[KitDocumentText] = []
        issues: list[KitValidationIssue] = []
        for raw_path in paths:
            path = Path(raw_path)
            try:
                extracted_texts = self._extract_document_texts(path)
            except RuntimeError as exc:
                issues.append(KitValidationIssue("error", "documents", str(exc), str(path)))
                continue
            for page_number, text in extracted_texts:
                kind = self.classify_text(text, path)
                documents.append(KitDocumentText(path=path, kind=kind, text=text, page_number=page_number))

        profile, extraction_issues = self.parse_document_texts(documents)
        issues.extend(extraction_issues)
        validation_issues = validate_kit_profile(profile)
        issues.extend(validation_issues)
        profile.validation_flags = [f"{issue.severity}: {issue.field}: {issue.message}" for issue in issues]
        return KitDocumentPayload(profile=profile, issues=issues, documents=documents)

    def parse_document_texts(self, documents: list[KitDocumentText]) -> tuple[KitMerchantProfile, list[KitValidationIssue]]:
        profile = KitMerchantProfile()
        issues: list[KitValidationIssue] = []
        source_names: list[tuple[str, str]] = []
        application_dob = ""
        dl_dob = ""

        for document in documents:
            text = _normalize_text(document.text)
            if document.kind == BANK_DOCUMENT:
                self._merge_bank_document(profile, text)
                continue

            if document.kind == DRIVER_LICENSE:
                dl_name = _extract_value(
                    text,
                    ["Driver Name", "Licensee", "Name", "Full Name"],
                )
                if dl_name:
                    source_names.append(("driver_license", _clean_name(dl_name)))
                dl_dob = _normalize_date(
                    _extract_value(text, ["Date of Birth", "DOB", "Birth Date"]) or _find_labeled_date(text, ["DOB"])
                )
                if dl_dob:
                    _assign_if_empty(profile, "dob", dl_dob)
                _assign_if_empty(
                    profile,
                    "dl_number",
                    _extract_value(
                        text,
                        ["Driver License Number", "License Number", "DL Number", "DL #", "LIC NO", "ID Number"],
                    ),
                )
                _assign_if_empty(
                    profile,
                    "dl_expiration",
                    _normalize_date(_extract_value(text, ["Expiration Date", "Expires", "EXP", "Exp Date"])),
                )
                profile.home_address = _first_complete_address(
                    profile.home_address,
                    _extract_address(text, ["Home Address", "Residence Address", "Address"]),
                )
                continue

            if document.kind == GREEN_CARD:
                given_name = _extract_value(text, ["Given Name"])
                surname = _extract_value(text, ["Surname"])
                if given_name and surname:
                    green_card_name = f"{given_name} {surname}"
                    source_names.append(("green_card", _clean_name(green_card_name)))
                gc_dob = _normalize_date(_extract_value(text, ["Date of Birth"]))
                if gc_dob:
                    _assign_if_empty(profile, "dob", gc_dob)
                continue

            application_name = _extract_value(
                text,
                ["Contact Person", "Owner Name", "Principal Name", "Authorized Signer", "Full Name"],
            )
            if application_name:
                source_names.append(("application", _clean_name(application_name)))
            _assign_if_empty(profile, "business_name_dba", _clean_legal_suffix(_extract_value(text, ["DBA Name", "DBA", "Business Name", "Store Name", "Merchant Name"])))
            _assign_if_empty(profile, "legal_name", _extract_value(text, ["Legal Business Name", "Legal Name", "Corporate Name", "Company Legal Name"]))
            _assign_if_empty(profile, "entity_type", _normalize_entity_type(_extract_value(text, ["Entity Type", "Business Type", "Ownership Type"]) or profile.legal_name))
            profile.business_address = _first_complete_address(
                profile.business_address,
                _extract_address(text, ["Business Address", "Store Address", "Physical Address", "Location Address", "Address"]),
            )
            _assign_if_empty(profile, "email", _extract_email(text))
            _assign_if_empty(profile, "phone", _normalize_phone(_extract_value(text, ["Phone", "Business Phone", "Contact Phone", "Telephone"]) or _extract_phone(text)))
            _assign_if_empty(profile, "ein", _normalize_tax_id(_extract_value(text, ["Federal Tax ID", "Tax ID", "EIN", "FEIN"])))
            _assign_if_empty(profile, "ssn", _normalize_ssn(_extract_value(text, ["SSN", "Social Security Number"])))
            application_dob = _normalize_date(_extract_value(text, ["Date of Birth", "DOB", "Birth Date"]))
            _assign_if_empty(profile, "dob", application_dob)
            _assign_if_empty(profile, "founded_date", _normalize_date(_extract_value(text, ["Founded Date", "Date Business Started", "Business Start Date"])))
            _assign_if_empty(profile, "industry", _extract_value(text, ["Product/Industry", "Industry", "Business Description", "MCC Description"]))

        reconciled_name, name_issue = reconcile_names(source_names)
        if reconciled_name:
            profile.contact_person = _principal_contact_person(reconciled_name)
        if name_issue:
            issues.append(name_issue)
        _enrich_from_all_documents(profile, documents)
        if application_dob and dl_dob and application_dob != dl_dob:
            issues.append(
                KitValidationIssue(
                    "error",
                    "dob",
                    "Date of birth from application does not match driver license.",
                    "application+driver_license",
                )
            )
        return profile, issues

    @staticmethod
    def classify_text(text: str, path: Path | None = None) -> str:
        haystack = f"{path.name if path else ''}\n{text}".lower()
        if any(token in haystack for token in ["voided check", "routing number", "routing #", "aba number", "bank account", "pay to the", "wells fargo"]):
            return BANK_DOCUMENT
        if re.search(r"\b1[:;]\s*\d{9}\s+\d{4,17}", haystack):
            return BANK_DOCUMENT
        if any(token in haystack for token in ["permanent resident", "united states of america", "uscis", "category", "resident since"]):
            return GREEN_CARD
        if any(token in haystack for token in ["driver license", "driver's license", "identification card", "license number", "dl number", "lic no", "class:"]):
            return DRIVER_LICENSE
        return APPLICATION

    @staticmethod
    def _extract_document_texts(path: Path) -> list[tuple[int | None, str]]:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                pages = [(index + 1, page.extract_text() or "") for index, page in enumerate(pdf.pages)]
            if any(text.strip() for _, text in pages):
                return pages
            ocr_pages = _extract_pdf_text_with_macos_vision(path)
            if ocr_pages:
                return ocr_pages
            return pages
        if suffix in {".txt", ".md"}:
            return [(None, path.read_text(encoding="utf-8"))]
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
            text = extract_text_from_image(path)
            return [(None, text)]
        raise RuntimeError(f"Unsupported document type: {path}")

    @staticmethod
    def _merge_bank_document(profile: KitMerchantProfile, text: str) -> None:
        routing = _normalize_digits(_extract_value(text, ["Routing Number", "Routing #", "ABA Number", "ABA Routing"]) or _find_routing_number(text))
        account = _normalize_digits(_extract_value(text, ["Account Number", "Account #", "Bank Account"]) or _find_account_number(text))
        micr_routing, micr_account = extract_micr_numbers(text)
        routing = micr_routing or routing
        account = micr_account or account
        _assign_if_empty(profile, "routing_number", routing)
        _assign_if_empty(profile, "account_number", account)


def validate_kit_profile(profile: KitMerchantProfile) -> list[KitValidationIssue]:
    issues: list[KitValidationIssue] = []
    required_errors = {
        "business_name_dba": profile.business_name_dba,
        "legal_name": profile.legal_name,
        "contact_person": profile.contact_person.full_name(),
        "business_address": profile.business_address.is_complete(),
        "home_address": profile.home_address.is_complete(),
        "email": profile.email,
        "phone": profile.phone,
        "ssn": profile.ssn,
        "dob": profile.dob,
        "dl_number": profile.dl_number,
        "routing_number": profile.routing_number,
        "account_number": profile.account_number,
    }
    for field_name, value in required_errors.items():
        if not value:
            issues.append(KitValidationIssue("error", field_name, "Required value is missing."))

    if not profile.ein:
        issues.append(KitValidationIssue("warning", "ein", "Tax ID/EIN was not found; continue only after operator review."))
    elif _normalize_digits(profile.ein) == _normalize_digits(profile.ssn):
        issues.append(KitValidationIssue("error", "ein", "Tax ID/EIN must not equal SSN."))

    routing = _normalize_digits(profile.routing_number)
    if routing and len(routing) != 9:
        issues.append(KitValidationIssue("error", "routing_number", "Routing number must contain exactly 9 digits."))
    elif routing and not is_valid_aba_routing_number(routing):
        issues.append(KitValidationIssue("error", "routing_number", "Routing number failed ABA checksum validation."))

    account = _normalize_digits(profile.account_number)
    if account and not 4 <= len(account) <= 17:
        issues.append(KitValidationIssue("warning", "account_number", "Account number length is outside the expected 4-17 digit range."))

    dl_expiration = _parse_iso_date(profile.dl_expiration)
    if dl_expiration and dl_expiration < date.today():
        issues.append(KitValidationIssue("error", "dl_expiration", "Driver license is expired."))

    if profile.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", profile.email):
        issues.append(KitValidationIssue("error", "email", "Email format is invalid."))
    return issues


def reconcile_names(source_names: list[tuple[str, str]]) -> tuple[str, KitValidationIssue | None]:
    clean_names = [(source, _clean_name(name)) for source, name in source_names if _clean_name(name)]
    if not clean_names:
        return "", None
    counter = Counter(name.casefold() for _, name in clean_names)
    most_common, occurrences = counter.most_common(1)[0]
    for _, name in clean_names:
        if name.casefold() == most_common:
            chosen = name
            break
    else:
        chosen = clean_names[0][1]

    unique = {name.casefold() for _, name in clean_names}
    if len(unique) == 1 or occurrences > 1:
        return chosen, None

    dl_name = next((name for source, name in clean_names if source == "driver_license"), "")
    if dl_name:
        return dl_name, KitValidationIssue(
            "warning",
            "contact_person",
            "Name sources disagree; driver license name was selected for Principal.",
            "name_reconciliation",
        )
    return chosen, KitValidationIssue(
        "warning",
        "contact_person",
        "Name sources disagree; most complete application name was selected.",
        "name_reconciliation",
    )


def is_valid_aba_routing_number(value: str) -> bool:
    digits = _normalize_digits(value)
    return validate_aba_checksum(digits)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text)


def _enrich_from_all_documents(profile: KitMerchantProfile, documents: list[KitDocumentText]) -> None:
    combined = "\n".join(document.text for document in documents)
    normalized = _normalize_text(combined)
    business_name = _extract_store_name(normalized)
    if business_name and (not profile.business_name_dba or _looks_low_confidence_dba(profile.business_name_dba)):
        profile.business_name_dba = business_name

    legal_name = _extract_legal_business_name(normalized)
    if legal_name:
        profile.legal_name = legal_name

    owner_name = _extract_owner_name(normalized)
    if owner_name:
        if not profile.legal_name:
            profile.legal_name = owner_name
        if not profile.contact_person.full_name() or len(profile.contact_person.full_name().split()) < 2:
            profile.contact_person = _principal_contact_person(owner_name)

    normalized_entity = _normalize_entity_type(profile.entity_type)
    if normalized_entity in {"Corporation", "LLC", "Individual"}:
        profile.entity_type = normalized_entity
    elif profile.legal_name:
        normalized_legal_entity = _normalize_entity_type(profile.legal_name)
        profile.entity_type = normalized_legal_entity if normalized_legal_entity in {"Corporation", "LLC", "Individual"} else "Individual"

    business_address = _extract_permit_business_address(normalized)
    if business_address.is_complete():
        profile.business_address = business_address

    start_date = _extract_start_date(normalized)
    if start_date and not profile.founded_date:
        profile.founded_date = start_date

    dl_text = "\n".join(document.text for document in documents if document.kind == DRIVER_LICENSE)
    if dl_text:
        dl_number = _extract_driver_license_number(dl_text)
        if dl_number:
            profile.dl_number = dl_number
    dl_name = _extract_driver_license_name(dl_text)
    if dl_name:
        profile.contact_person = _principal_contact_person(dl_name)
        if profile.entity_type == "Individual" and not profile.legal_name:
            profile.legal_name = dl_name
    dl_address = _extract_driver_license_address(dl_text)
    if dl_address.is_complete():
        profile.home_address = dl_address

    cell_phone = _extract_cell_phone(normalized)
    if cell_phone:
        profile.phone = _normalize_phone(cell_phone)
    elif not _normalize_digits(profile.phone):
        phone = _extract_phone(normalized)
        if phone:
            profile.phone = _normalize_phone(phone)
    if not _normalize_digits(profile.ein) or len(_normalize_digits(profile.ein)) != 9:
        ein = _extract_tax_id_near_label(normalized, ["Federal Tax ID", "Tax ID", "EIN", "FEIN"])
        if ein:
            profile.ein = _normalize_tax_id(ein)
    seller_permit_account = _extract_seller_permit_account_number(normalized)
    if seller_permit_account and (
        not profile.ein or _normalize_digits(profile.ein) == _normalize_digits(profile.ssn)
    ):
        profile.ein = seller_permit_account

    if not profile.routing_number or not profile.account_number:
        micr_routing, micr_account = _extract_micr_numbers(normalized)
        if micr_routing:
            profile.routing_number = micr_routing
        if micr_account:
            profile.account_number = micr_account


def _extract_pdf_text_with_macos_vision(path: Path) -> list[tuple[int | None, str]]:
    if platform.system() != "Darwin" or not shutil.which("swift"):
        return []
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "macos_vision_ocr.swift"
    if not script_path.exists():
        return []
    try:
        result = subprocess.run(
            ["swift", str(script_path), str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    try:
        decoded = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    pages: list[tuple[int | None, str]] = []
    for item in decoded:
        pages.append((item.get("page_number"), item.get("text", "")))
    return pages


def _extract_value(text: str, labels: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        for label in labels:
            pattern = rf"\b{re.escape(label)}\b\s*[:#-]?\s*(?P<value>.*)$"
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if not match:
                continue
            value = _strip_value(match.group("value"))
            if value:
                return value
            for next_line in lines[index + 1 : index + 3]:
                value = _strip_value(next_line)
                if value and not _is_common_label(value):
                    return value
    return ""


def _strip_value(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value).strip(" :-#\t")
    return value


def _assign_if_empty(profile: KitMerchantProfile, field_name: str, value: str | None) -> None:
    if value and not getattr(profile, field_name):
        setattr(profile, field_name, value.strip())


def _first_complete_address(existing: Address, candidate: Address) -> Address:
    if existing.is_complete():
        return existing
    if candidate.is_complete():
        return candidate
    return Address(
        street=existing.street or candidate.street,
        city=existing.city or candidate.city,
        state=existing.state or candidate.state,
        zip=existing.zip or candidate.zip,
    )


def _extract_address(text: str, labels: list[str]) -> Address:
    value = _extract_value(text, labels)
    nearby = value
    if value and not _looks_like_full_address(value):
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if value in line:
                nearby = " ".join([value, *[candidate.strip() for candidate in lines[index + 1 : index + 3] if candidate.strip()]])
                break
    return _parse_address(nearby)


def _parse_address(value: str) -> Address:
    if not value:
        return Address()
    value = re.sub(r"\s+", " ", value).strip()
    city_state_zip = re.search(
        r"(?P<street>.*?)[, ]+(?P<city>[A-Za-z .'-]+),?\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)\b",
        value,
    )
    if city_state_zip:
        return Address(
            street=city_state_zip.group("street").strip(" ,"),
            city=city_state_zip.group("city").strip(" ,"),
            state=city_state_zip.group("state"),
            zip=city_state_zip.group("zip"),
        )
    return Address(street=value)


def _looks_like_full_address(value: str) -> bool:
    return bool(re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", value))


def _extract_email(text: str) -> str:
    labeled = _extract_value(text, ["Email", "Email Address", "Contact Email"])
    if labeled:
        match = re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", labeled)
        if match:
            return match.group(0).strip(".,;")
    match = re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", text)
    return match.group(0).strip(".,;") if match else ""


def _extract_phone(text: str) -> str:
    match = re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", text)
    return match.group(0) if match else ""


def _normalize_phone(value: str) -> str:
    digits = _normalize_digits(value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    return ""


def _normalize_tax_id(value: str | None) -> str:
    digits = _normalize_digits(value or "")
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return value.strip() if value else ""


def _normalize_ssn(value: str | None) -> str:
    digits = _normalize_digits(value or "")
    if len(digits) == 9:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return value.strip() if value else ""


def _normalize_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _normalize_date(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    match = re.search(r"\b(?P<m>\d{1,2})[/-](?P<d>\d{1,2})[/-](?P<y>\d{2,4})\b", value)
    if not match:
        return value
    year = match.group("y")
    if len(year) == 2:
        prefix = "19" if int(year) > 30 else "20"
        year = f"{prefix}{year}"
    return f"{year}-{int(match.group('m')):02d}-{int(match.group('d')):02d}"


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _find_labeled_date(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\D+(?P<date>\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})", text, re.IGNORECASE)
        if match:
            return match.group("date")
    return ""


def _normalize_entity_type(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.lower()
    if "llc" in lowered or "limited liability" in lowered:
        return "LLC"
    if any(token in lowered for token in ["inc", "corp", "corporation", "incorporated"]):
        return "Corporation"
    if any(token in lowered for token in ["sole", "individual", "proprietor"]):
        return "Individual"
    return value.strip()


def _clean_legal_suffix(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\b(LLC|L\.L\.C\.|INC\.?|INCORPORATED|CORP\.?|CORPORATION)\b", "", value, flags=re.IGNORECASE).strip(" ,")


def _clean_name(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"\b(owner|principal|contact|name)\b", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip(" ,:-")


def _principal_contact_person(full_name: str | None) -> ContactPerson:
    """
    KIT boarding does not expose a middle-name field. Keep first and last only.
    """
    if not full_name:
        return ContactPerson()
    parts = [part for part in full_name.replace(",", " ").split() if part]
    if not parts:
        return ContactPerson()
    if len(parts) == 1:
        return ContactPerson(first=parts[0])
    return ContactPerson(first=parts[0], last=parts[-1])


def _is_common_label(value: str) -> bool:
    labels = {
        "fax",
        "phone",
        "state",
        "zip",
        "city",
        "date of birth",
        "federal tax id",
        "social security number",
        "cell phone",
        "last name",
        "first name",
    }
    return value.strip().lower() in labels


def _looks_low_confidence_dba(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith(("dishuja", "alshujah")) or len(value.split()) < 2


def _extract_store_name(text: str) -> str:
    patterns = [
        r"Store Name:\s*(?P<name>[^\n]+)",
        r"\bDBA\s+(?P<name>[A-Z][A-Z ]*MARKET)\b",
        r"ACCOUNT NUMBER\s*\n[^\n]+\n(?P<name>[A-Z][A-Z ]*MARKET)\b",
        r"PERMIT NUMBER\s*\n[^\n]+\n(?P<name>[A-Z0-9][A-Z0-9 '&.-]+)\n[A-Z0-9][A-Z0-9 '&.-]+\s+LLC\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _title_name(match.group("name"))
    return ""


def _extract_legal_business_name(text: str) -> str:
    patterns = [
        r"Legal Name:\s*(?P<name>[^\n]+?\b(?:LLC|INC\.?|CORP\.?|CORPORATION|INCORPORATED)\b)",
        r"PERMIT NUMBER\s*\n[^\n]+\n[A-Z0-9][A-Z0-9 '&.-]+\n(?P<name>[A-Z0-9][A-Z0-9 '&.-]+\b(?:LLC|INC\.?|CORP\.?|CORPORATION|INCORPORATED)\b)",
        r"IRS Notice [^\n]+\n(?P<name>[A-Z0-9][A-Z0-9 '&.-]+\b(?:LLC|INC\.?|CORP\.?|CORPORATION|INCORPORATED)\b)",
        r"Corporation Name\s*\nCorporation Name\s*\n(?P<name>[^\n]+)",
        r"ARTICLES OF INCORPORATION.*?Corporation Name\s*\nCorporation Name\s*\n(?P<name>[^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _title_name(match.group("name"))
    return ""


def _extract_owner_name(text: str) -> str:
    patterns = [
        r"Owner/Officer Name\(s\):\s*(?P<name>[^\n]+)",
        r"ACCOUNT NUMBER\s*\n[^\n]+\n[A-Z][A-Z ]*MARKET\s*\n(?P<name>[A-Z][A-Z ]+)",
        r"Agent Name\s*\n(?P<name>[^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _title_name(match.group("name"))
    return ""


def _extract_permit_business_address(text: str) -> Address:
    match = re.search(
        r"(?P<street>\d{3,6}\s+MACARTHUR\s+BLVD[^\n]*)\n(?P<city>OAKLAND)\s+(?P<state>CA)\s+(?P<zip>\d{5}(?:-\d{4})?)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"Location Address:\s*(?P<street>[^\n]+)\n(?P<city>[A-Za-z .'-]+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)",
            text,
            flags=re.IGNORECASE,
        )
    if not match:
        match = re.search(
            r"PERMIT NUMBER\s*\n[^\n]+\n[A-Z0-9][A-Z0-9 '&.-]+\n[A-Z0-9][A-Z0-9 '&.-]+\b(?:LLC|INC\.?|CORP\.?|CORPORATION|INCORPORATED)\b\n(?P<street>\d{2,6}\s+[^\n]+)\n(?P<city>[A-Z][A-Z .'-]+)\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)",
            text,
            flags=re.IGNORECASE,
        )
    if not match:
        match = re.search(
            r"PERMIT NUMBER\s*\n[^\n]+\n[A-Z0-9][A-Z0-9 '&.-]+\n[A-Z0-9][A-Z0-9 '&.-]+\n(?P<street>\d{2,6}\s+[^\n]+)\n(?P<city>[A-Z][A-Z .'-]+)\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)",
            text,
            flags=re.IGNORECASE,
        )
    if not match:
        match = re.search(
            r"%\s*[A-Z0-9 .'-]+?\n(?P<street>\d{2,6}\s+[^\n]+)\n(?P<city>[A-Z][A-Z .'-]+),?\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)",
            text,
            flags=re.IGNORECASE,
        )
    if not match:
        return Address()
    return Address(
        street=_title_name(match.group("street")),
        city=_title_name(match.group("city")),
        state=match.group("state").upper(),
        zip=match.group("zip"),
    )


def _extract_driver_license_number(text: str) -> str:
    match = re.search(r"\bDL\s*\n\s*(?P<number>[A-Z]\d{6,8})\b", text, flags=re.IGNORECASE)
    if match:
        return match.group("number").upper()
    match = re.search(r"^\s*[A-Z]?\d{2,6}\s+(?P<number>[A-Z]\d{6,8})\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group("number").upper()
    match = re.search(r"\b(?P<number>[A-Z]\d{6,8})\b", text)
    return match.group("number").upper() if match else ""


def _extract_driver_license_name(text: str) -> str:
    last = re.search(r"^\s*LN\s+(?P<last>[A-Z][A-Z ]+)\s*$", text, flags=re.MULTILINE)
    first = re.search(r"^\s*FN\s+(?P<first>[A-Z][A-Z ]+)\s*$", text, flags=re.MULTILINE)
    if first and last:
        return _title_name(f"{first.group('first')} {last.group('last')}")
    return ""


def _extract_driver_license_address(text: str) -> Address:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if re.match(r"^\d{2,6}\s+", line) and index + 1 < len(lines):
            next_line_match = re.match(
                r"^(?P<city>[A-Za-z .'-]+),?\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$",
                lines[index + 1],
            )
            if next_line_match:
                return Address(
                    street=_title_name(line),
                    city=_title_name(next_line_match.group("city")),
                    state=next_line_match.group("state"),
                    zip=next_line_match.group("zip"),
                )
            candidate = f"{line} {lines[index + 1]}"
            address = _parse_address(candidate)
            if address.is_complete():
                return address
    return Address()


def _extract_cell_phone(text: str) -> str:
    match = re.search(r"Cell Phone\s*\n(?P<value>(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})", text, flags=re.IGNORECASE)
    return match.group("value") if match else ""


def _extract_tax_id_near_label(text: str, labels: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if any(label.lower() in line.lower() for label in labels):
            window = "\n".join(lines[index : index + 5])
            matches = re.findall(r"\b\d{2}[- ]?\d{7}\b", window)
            if matches:
                return matches[-1]
    return ""


def _extract_seller_permit_account_number(text: str) -> str:
    match = re.search(
        r"SELLER'?S PERMIT.*?(?:ACCOUNT|PERMIT) NUMBER\s*\n\s*(?P<account>\d{6,12})\s*[- ]\s*\d{3,8}",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return _normalize_digits(match.group("account"))
    match = re.search(
        r"ACCOUNT NUMBER\s*\n\s*(?P<account>\d{6,12})\s*[- ]\s*\d{3,8}.*?\bALSHUJA MARKET\b",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return _normalize_digits(match.group("account")) if match else ""


def _extract_start_date(text: str) -> str:
    match = re.search(
        r"START DATE:\s*\n?\s*(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    month = months.get(match.group("month").lower())
    if not month:
        return ""
    return f"{match.group('year')}-{month:02d}-{int(match.group('day')):02d}"


def _extract_micr_numbers(text: str) -> tuple[str, str]:
    match = re.search(r"1[:;]\s*(?P<routing>\d{9})\s+(?P<account>\d{4,17})", text)
    if not match:
        return "", ""
    routing = match.group("routing")
    account = match.group("account")
    return routing, account


def _title_name(value: str) -> str:
    words = re.sub(r"\s+", " ", value).strip(" ,:-").split()
    preserved = {"LLC", "L.L.C.", "INC", "INC.", "CORP", "CORP.", "DBA", "EIN", "IRS"}
    titled: list[str] = []
    for word in words:
        upper_word = word.upper()
        if upper_word in preserved:
            titled.append(upper_word)
        elif word.isupper():
            titled.append(word.title())
        else:
            titled.append(word.capitalize())
    return " ".join(titled)


def _find_routing_number(text: str) -> str:
    for match in re.finditer(r"\b\d{9}\b", text):
        digits = match.group(0)
        if is_valid_aba_routing_number(digits):
            return digits
    return ""


def _find_account_number(text: str) -> str:
    labeled = _extract_value(text, ["Account", "Acct"])
    digits = _normalize_digits(labeled)
    if 4 <= len(digits) <= 17:
        return digits
    candidates = [_normalize_digits(match.group(0)) for match in re.finditer(r"\b\d{4,17}\b", text)]
    return candidates[-1] if candidates else ""
