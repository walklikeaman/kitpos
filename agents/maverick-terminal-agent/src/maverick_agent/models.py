from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MerchantRequest:
    merchant_id: str
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


@dataclass(slots=True)
class TaskField:
    key: str
    value: str
    source: str


@dataclass(slots=True)
class RunPlan:
    merchant_display_name: str
    terminal_display_name: str
    merchant_id: str
    serial_number: str
    pdf_path: Path | None
    extracted_fields: dict[str, str]
    task_fields: list[TaskField]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pdf_path"] = str(self.pdf_path) if self.pdf_path else None
        return data


@dataclass(slots=True)
class RunOutcome:
    status: str
    message: str
    next_action: str | None = None
    plan: RunPlan | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.plan:
            data["plan"] = self.plan.to_dict()
        return data


@dataclass(slots=True)
class Address:
    street: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""

    def is_complete(self) -> bool:
        return bool(self.street and self.city and self.state and self.zip)


@dataclass(slots=True)
class ContactPerson:
    first: str = ""
    last: str = ""

    @classmethod
    def from_full_name(cls, full_name: str | None) -> "ContactPerson":
        if not full_name:
            return cls()
        parts = [part for part in full_name.replace(",", " ").split() if part]
        if not parts:
            return cls()
        if len(parts) == 1:
            return cls(first=parts[0])
        return cls(first=parts[0], last=" ".join(parts[1:]))

    def full_name(self) -> str:
        return " ".join(part for part in [self.first, self.last] if part)


def mask_digits(value: str, *, visible: int = 4) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= visible:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - visible)}{digits[-visible:]}"
