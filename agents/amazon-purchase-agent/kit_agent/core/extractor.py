"""
PDF data extractor — uses Claude vision to read documents.

Design:
  - Each document type (application, DL, check) has its own extraction prompt
  - The LLM is explicitly instructed to reason about ambiguities
  - Results are validated before use; the LLM explains its confidence
  - No regex hard-codes for document parsing — the LLM handles variation

Extraction flow:
  1. Convert each PDF page to base64 image
  2. Classify the page (application / DL / check / other)
  3. Extract structured fields per classification rules from config.yaml
  4. Cross-reference fields across documents (name, DOB, address)
  5. Return a validated MerchantProfile
"""
from __future__ import annotations
import base64
import json
import re
from pathlib import Path
from typing import Any

import anthropic

from .config import get_config
from .logger import SessionLogger


_SYSTEM_PROMPT = """
You are an expert document processing AI for merchant onboarding.
You extract structured data from PDFs with high precision.

Critical rules:
1. Read routing/account numbers ONLY from the MICR line at the bottom of checks
   (the special magnetic ink characters at the very bottom strip)
2. For principal names: prefer the short name from the application form
   over the full legal name from the Driver License
3. Home address = from Driver License (residential). Business address = from application form.
   These are DIFFERENT — never confuse them.
4. For phone: use the phone from the "Owner's Information" or "Principal" section,
   not the general business phone
5. If you are uncertain about a value, set confidence to "low" and explain why
6. Always output valid JSON — no markdown, no explanations outside the JSON
"""


class ExtractionError(Exception):
    pass


class MerchantExtractor:
    def __init__(self, log: SessionLogger):
        cfg = get_config()
        self.log = log
        self.cfg = cfg
        api_key = cfg.get("anthropic", {}).get("api_key", "")
        if not api_key:
            raise ExtractionError("ANTHROPIC_API_KEY not set in .env")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-opus-4-7"  # Most capable for vision tasks

    def extract_from_pdf(self, pdf_path: Path) -> dict:
        """
        Main entry point: extract merchant profile from a PDF with multiple pages.
        Returns a validated merchant_profile dict.
        """
        self.log.step("PDF Extraction")
        pages = self._pdf_to_images(pdf_path)
        self.log.info(f"PDF has {len(pages)} pages")

        # Step 1: classify all pages
        classified = self._classify_pages(pages)
        self.log.info(f"Page classification: {classified}")

        # Step 2: extract from each relevant page
        app_pages = [pages[i] for i, t in classified.items() if t == "application"]
        dl_pages = [pages[i] for i, t in classified.items() if t == "driver_license"]
        check_pages = [pages[i] for i, t in classified.items() if t == "voided_check"]

        profile = {}

        if app_pages:
            app_data = self._extract_application(app_pages)
            profile.update(app_data)
            self.log.info("Application form extracted", {"fields": list(app_data.keys())})

        if dl_pages:
            dl_data = self._extract_driver_license(dl_pages)
            profile = self._merge_dl(profile, dl_data)
            self.log.info("Driver license extracted", {"dl_number": dl_data.get("dl_number")})

        if check_pages:
            check_data = self._extract_check(check_pages)
            profile.update({
                "routing_number": check_data.get("routing_number", ""),
                "account_number": check_data.get("account_number", ""),
                "bank_name": check_data.get("bank_name", ""),
            })
            self.log.info("Check extracted", {
                "routing": profile.get("routing_number"),
                "account": profile.get("account_number"),
            })

        # Step 3: cross-validate and flag issues
        profile["validation_flags"] = self._validate(profile)

        self.log.extracted_profile(profile)
        return profile

    # ── Page classification ─────────────────────────────────────────────────

    def _classify_pages(self, pages: list[str]) -> dict[int, str]:
        """Ask the LLM to classify each page type."""
        page_images = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": p}}
            for p in pages
        ]
        prompt = (
            "Classify each page in this PDF. For each page (numbered 0-based), "
            "respond with one of: application, driver_license, voided_check, ein_letter, "
            "articles_of_incorporation, sellers_permit, other.\n\n"
            "Respond with ONLY a JSON object like: {\"0\": \"application\", \"1\": \"driver_license\"}"
        )
        result = self._call_vision(page_images[:6], prompt)  # max 6 pages
        try:
            return {int(k): v for k, v in json.loads(result).items()}
        except Exception:
            # Fallback: assume first page is application
            self.log.warn("Page classification failed, using fallback order")
            return {i: ["application", "driver_license", "voided_check"][min(i, 2)]
                    for i in range(len(pages))}

    # ── Extraction per document type ────────────────────────────────────────

    def _extract_application(self, page_images: list[str]) -> dict:
        ext_cfg = self.cfg["extraction"]["application_form"]
        fields = ext_cfg["fields"]

        prompt = f"""
Extract the following fields from this merchant application form: {fields}

Return ONLY a JSON object. For each field, include:
  "value": the extracted value (string/number)
  "confidence": "high" | "medium" | "low"
  "note": explanation if confidence is not high

Special instructions:
- entity_type: must be one of: Individual, Partnership, Corporation, Government, LLC, Non-Profit, Publicly-Traded
- phone_owner: extract ONLY from the "Owner's Information" or "Principal" section — not business phone
- ein: 9 digits only, no dashes
- founded_date: format as YYYY-MM-DD; if only year known, use YYYY-01-01

Example output:
{{
  "business_name_dba": {{"value": "Snack Zone", "confidence": "high", "note": null}},
  "phone_owner": {{"value": "5106402004", "confidence": "high", "note": "From Owner Information section"}},
  ...
}}
"""
        raw = self._call_vision(
            [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": p}}
             for p in page_images],
            prompt
        )
        return self._flatten_confident(raw, fields)

    def _extract_driver_license(self, page_images: list[str]) -> dict:
        ext_cfg = self.cfg["extraction"]["driver_license"]
        fields = ext_cfg["fields"]

        prompt = f"""
Extract these fields from the Driver License: {fields}

Critical:
- home_address: the RESIDENTIAL address printed on the DL — this is different from business address
- first_name / last_name: exactly as printed on the DL
- dl_expiration: format MM/DD/YYYY
- dob: format MM/DD/YYYY

Return ONLY JSON:
{{
  "dl_number": {{"value": "...", "confidence": "high"}},
  "home_address": {{"value": "1647 8th St", "confidence": "high"}},
  "home_city": {{"value": "...", "confidence": "high"}},
  "home_state": {{"value": "CA", "confidence": "high"}},
  "home_zip": {{"value": "...", "confidence": "high"}},
  ...
}}
"""
        raw = self._call_vision(
            [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": p}}
             for p in page_images],
            prompt
        )
        return self._flatten_confident(raw, fields)

    def _extract_check(self, page_images: list[str]) -> dict:
        micr_instruction = self.cfg["extraction"]["voided_check"]["micr_line_instructions"]

        prompt = f"""
Extract routing and account numbers from this voided check.

{micr_instruction}

Return ONLY JSON:
{{
  "routing_number": {{"value": "XXXXXXXXX", "confidence": "high", "note": "From MICR line"}},
  "account_number": {{"value": "XXXXXXXXXXXX", "confidence": "high", "note": "From MICR line"}},
  "bank_name": {{"value": "...", "confidence": "high"}}
}}

CRITICAL: routing must be exactly 9 digits. If you see more or fewer, recheck from MICR line.
"""
        raw = self._call_vision(
            [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": p}}
             for p in page_images],
            prompt
        )
        return self._flatten_confident(raw, ["routing_number", "account_number", "bank_name"])

    # ── Cross-document merge ────────────────────────────────────────────────

    def _merge_dl(self, profile: dict, dl: dict) -> dict:
        """
        Merge DL data into profile.
        Name rule: use application form name (short) + DL last name as fallback.
        Address rule: DL address = home address (separate from business).
        """
        # Home address always from DL
        profile["home_address"] = {
            "street": dl.get("home_address", ""),
            "city": dl.get("home_city", ""),
            "state": dl.get("home_state", ""),
            "zip": dl.get("home_zip", ""),
        }

        # DL fields
        profile["dl_number"] = dl.get("dl_number", "")
        profile["dl_expiration"] = dl.get("dl_expiration", "")

        # DOB cross-check
        dl_dob = dl.get("dob", "")
        app_dob = profile.get("dob", "")
        if dl_dob and app_dob and dl_dob != app_dob:
            profile.setdefault("validation_flags", []).append(
                f"DOB mismatch: application={app_dob}, DL={dl_dob}"
            )
        profile["dob"] = app_dob or dl_dob

        # Name reconciliation: prefer application form, use DL only for last name fallback
        dl_first = dl.get("first_name", "")
        dl_last = dl.get("last_name", "")
        contact = profile.get("contact_person", {})
        if not contact.get("first") and dl_first:
            contact["first"] = dl_first
        if not contact.get("last") and dl_last:
            contact["last"] = dl_last
        profile["contact_person"] = contact

        return profile

    # ── Validation ──────────────────────────────────────────────────────────

    def _validate(self, profile: dict) -> list[str]:
        flags = list(profile.get("validation_flags", []))
        v = self.cfg["validation"]

        routing = re.sub(r"\D", "", profile.get("routing_number", ""))
        account = re.sub(r"\D", "", profile.get("account_number", ""))
        ein = re.sub(r"\D", "", profile.get("ein", ""))
        ssn = re.sub(r"\D", "", profile.get("ssn", ""))

        if len(routing) != v["routing_number"]["digits"]:
            flags.append(f"Routing number should be 9 digits, got {len(routing)}: '{routing}'")

        acc_min = v["account_number"]["min_digits"]
        acc_max = v["account_number"]["max_digits"]
        if not (acc_min <= len(account) <= acc_max):
            flags.append(f"Account number digit count {len(account)} out of range {acc_min}-{acc_max}: '{account}'")

        if len(ein) != v["ein"]["digits"]:
            flags.append(f"EIN should be 9 digits, got {len(ein)}: '{ein}'")

        if ein and ssn and ein == ssn:
            flags.append("CRITICAL: EIN equals SSN — must not proceed until resolved")

        if not profile.get("contact_person", {}).get("first"):
            flags.append("Missing principal first name")

        if not profile.get("home_address", {}).get("street"):
            flags.append("Missing home address (should come from Driver License)")

        return flags

    # ── LLM call ────────────────────────────────────────────────────────────

    def _call_vision(self, images: list[dict], prompt: str) -> str:
        """Call Claude with images + prompt, return raw text response."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": images + [{"type": "text", "text": prompt}],
            }],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return text

    def _flatten_confident(self, raw_json: str, fields: list[str]) -> dict:
        """
        Parse LLM JSON response and flatten confidence-annotated fields.
        Low-confidence fields are flagged but still included.
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            self.log.warn("LLM returned invalid JSON, attempting partial parse")
            data = self._partial_parse(raw_json)

        result = {}
        for field in fields:
            if field not in data:
                continue
            entry = data[field]
            if isinstance(entry, dict):
                value = entry.get("value", "")
                confidence = entry.get("confidence", "high")
                note = entry.get("note", "")
                if confidence == "low":
                    self.log.warn(f"Low confidence for '{field}': {note or 'no note'}")
            else:
                value = entry  # LLM returned plain value

            result[field] = str(value).strip() if value is not None else ""

        # Remap phone_owner → phone
        if "phone_owner" in result:
            result["phone"] = result.pop("phone_owner")

        # Build structured address from flat fields
        if "business_address" not in result and "city" in result:
            result["business_address"] = {
                "street": result.pop("business_address", result.pop("address", "")),
                "city": result.pop("city", ""),
                "state": result.pop("state", ""),
                "zip": result.pop("zip", ""),
            }

        return result

    def _partial_parse(self, text: str) -> dict:
        """Best-effort extraction when JSON is malformed."""
        result = {}
        for m in re.finditer(r'"(\w+)"\s*:\s*\{\s*"value"\s*:\s*"([^"]*)"', text):
            result[m.group(1)] = {"value": m.group(2), "confidence": "medium"}
        return result

    # ── PDF → Images ────────────────────────────────────────────────────────

    def _pdf_to_images(self, pdf_path: Path) -> list[str]:
        """Convert PDF pages to base64 PNG images using PyMuPDF (fitz)."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(pdf_path))
            images = []
            for page in doc:
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
                pix = page.get_pixmap(matrix=mat)
                images.append(base64.b64encode(pix.tobytes("png")).decode())
            return images
        except ImportError:
            self.log.warn("PyMuPDF not installed — falling back to pdf2image")
            return self._pdf_to_images_fallback(pdf_path)

    def _pdf_to_images_fallback(self, pdf_path: Path) -> list[str]:
        """Fallback: use pdf2image (requires poppler)."""
        try:
            from pdf2image import convert_from_path
            import io
            pages = convert_from_path(str(pdf_path), dpi=200)
            images = []
            for page in pages:
                buf = io.BytesIO()
                page.save(buf, format="PNG")
                images.append(base64.b64encode(buf.getvalue()).decode())
            return images
        except ImportError:
            raise ExtractionError(
                "Neither PyMuPDF nor pdf2image is installed. "
                "Run: pip install PyMuPDF  (or: pip install pdf2image)"
            )
