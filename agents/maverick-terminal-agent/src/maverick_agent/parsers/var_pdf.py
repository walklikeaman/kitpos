from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from maverick_agent.models import VarPayload


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ALIAS_FILE = PROJECT_ROOT / "config" / "field_aliases.json"
REQUIRED_FIELDS = [
    "dba_name",
    "merchant_number",
    "bin",
    "base_identification_number",
    "vin",
    "chain",
    "agent_bank",
    "store_number",
    "terminal_number",
    "location_number",
]


@dataclass(slots=True)
class VarPdfParser:
    alias_file: Path = DEFAULT_ALIAS_FILE

    def parse_file(self, pdf_path: Path | str) -> VarPayload:
        import pdfplumber

        pdf_path = Path(pdf_path)
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        payload = self.parse_text(text)
        payload.source_path = pdf_path
        return payload

    def parse_text(self, text: str) -> VarPayload:
        alias_map = self._load_alias_map()
        normalized_text = self._normalize_text(text)
        fields: dict[str, str] = {}
        for field_name, aliases in alias_map.items():
            value = self._extract_labeled_value(normalized_text, aliases)
            if value:
                fields[field_name] = value

        terminal_id = self._derive_terminal_id(fields.get("vin"))
        if terminal_id:
            fields["terminal_id_number"] = terminal_id

        missing_required = [name for name in REQUIRED_FIELDS if not fields.get(name)]
        return VarPayload(source_path=None, fields=fields, missing_required=missing_required)

    def _load_alias_map(self) -> dict[str, list[str]]:
        with self.alias_file.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        return text

    @staticmethod
    def _extract_labeled_value(text: str, aliases: list[str]) -> str | None:
        patterns = [
            r"{label}\s*[:#-]?\s*(?P<value>[^\n]+)",
            r"{label}\s*\n\s*(?P<value>[^\n]+)",
        ]
        for alias in aliases:
            safe_alias = re.escape(alias)
            for template in patterns:
                pattern = template.format(label=safe_alias)
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    value = match.group("value").strip()
                    if value:
                        return value
        return None

    @staticmethod
    def _derive_terminal_id(vin: str | None) -> str | None:
        if not vin:
            return None
        vin = vin.strip()
        if vin.startswith("V") and len(vin) > 1:
            return "7" + vin[1:]
        if vin and not vin.startswith("7"):
            return "7" + vin
        return vin
