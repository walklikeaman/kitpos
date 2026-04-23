from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


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


@dataclass(slots=True)
class KitMerchantProfile:
    business_name_dba: str = ""
    legal_name: str = ""
    entity_type: str = ""
    business_address: Address = field(default_factory=Address)
    home_address: Address = field(default_factory=Address)
    contact_person: ContactPerson = field(default_factory=ContactPerson)
    email: str = ""
    phone: str = ""
    ein: str = ""
    ssn: str = ""
    dob: str = ""
    dl_number: str = ""
    dl_expiration: str = ""
    routing_number: str = ""
    account_number: str = ""
    founded_date: str = ""
    industry: str = ""
    validation_flags: list[str] = field(default_factory=list)

    def to_dict(self, *, mask_sensitive: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if mask_sensitive:
            data["ssn"] = mask_digits(self.ssn)
            data["ein"] = mask_digits(self.ein)
            data["account_number"] = mask_digits(self.account_number)
        return data


@dataclass(slots=True)
class KitValidationIssue:
    severity: str
    field: str
    message: str
    source: str = "validation"


@dataclass(slots=True)
class KitDocumentText:
    path: Path
    kind: str
    text: str
    page_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "page_number": self.page_number,
            "text_length": len(self.text),
        }


@dataclass(slots=True)
class KitDocumentPayload:
    profile: KitMerchantProfile
    issues: list[KitValidationIssue] = field(default_factory=list)
    documents: list[KitDocumentText] = field(default_factory=list)

    def to_dict(self, *, mask_sensitive: bool = True) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(mask_sensitive=mask_sensitive),
            "issues": asdict(self)["issues"],
            "documents": [document.to_dict() for document in self.documents],
        }


@dataclass(slots=True)
class KitOnboardingPlan:
    profile: KitMerchantProfile
    application_defaults: dict[str, str]
    dashboard_steps: list[str]
    issues: list[KitValidationIssue] = field(default_factory=list)

    def to_dict(self, *, mask_sensitive: bool = True) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(mask_sensitive=mask_sensitive),
            "application_defaults": self.application_defaults,
            "dashboard_steps": self.dashboard_steps,
            "issues": asdict(self)["issues"],
        }


@dataclass(slots=True)
class KitOnboardingOutcome:
    status: str
    message: str
    next_action: str | None = None
    plan: KitOnboardingPlan | None = None

    def to_dict(self, *, mask_sensitive: bool = True) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "next_action": self.next_action,
            "plan": self.plan.to_dict(mask_sensitive=mask_sensitive) if self.plan else None,
        }
