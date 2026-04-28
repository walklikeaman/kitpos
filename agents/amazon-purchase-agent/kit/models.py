from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
    address: str = ""          # full shipping address, e.g. "123 Main St, City, ST 12345"
    raw_fields: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Merchant:   {self.merchant_name}",
            f"ID:         {self.merchant_id}",
            f"Principal:  {self.principal_name or '(not found)'}",
            f"Phone:      {self.phone or '(not found)'}",
            f"Email:      {self.email or '(not found)'}",
            f"Address:    {self.address or '(not found)'}",
            f"Profile:    {self.profile_url}",
        ]
        return "\n".join(lines)

    def to_ship_to(self) -> str:
        """Format as a shipping address string for the Amazon agent."""
        parts = [self.principal_name or self.merchant_name]
        if self.address:
            parts.append(self.address)
        if self.phone:
            parts.append(self.phone)
        return ", ".join(p for p in parts if p)
