from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class VarDownloadResult:
    merchant_name: str
    search_term: str
    profile_url: str
    saved_path: Path

    def summary(self) -> str:
        lines = [
            f"Merchant:   {self.merchant_name}",
            f"Search:     {self.search_term}",
            f"Profile:    {self.profile_url}",
            f"VAR file:   {self.saved_path}",
        ]
        return "\n".join(lines)


@dataclass(slots=True)
class KitCredentials:
    email: str
    password: str
    base_url: str = "https://kitdashboard.com/"
    storage_state: Path = Path("tmp/kit-merchant-state.json")
    verification_code: str | None = None


@dataclass(slots=True)
class MerchantResult:
    merchant_id: str
    merchant_name: str
    profile_url: str
    principal_name: str
    phone: str
    email: str
    raw_fields: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Merchant:   {self.merchant_name}",
            f"ID:         {self.merchant_id}",
            f"Principal:  {self.principal_name or '(not found)'}",
            f"Phone:      {self.phone or '(not found)'}",
            f"Email:      {self.email or '(not found)'}",
            f"Profile:    {self.profile_url}",
        ]
        return "\n".join(lines)
