from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MerchantRequest:
    merchant_number: str
    serial_number: str
    pdf_path: Path | None = None


@dataclass(slots=True)
class AttachmentCandidate:
    filename: str
    path: Path
    subject: str
    sender: str


@dataclass(slots=True)
class VarPayload:
    source_path: Path | None
    fields: dict[str, str] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_path"] = str(self.source_path) if self.source_path else None
        return data
