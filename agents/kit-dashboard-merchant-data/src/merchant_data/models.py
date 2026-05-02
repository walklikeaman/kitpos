from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# BIN is determined by Chain (acquiring bank group), not per merchant.
# Derived from comparing multiple VAR sheets.
_CHAIN_TO_BIN: dict[str, str] = {
    "081960": "422108",  # FFB Bank / main KIT POS chain
    "261960": "442114",  # e.g. Ali Baba Smoke and Gift Shop
    "051960": "403982",  # e.g. Holy Smokes Smoke Shop
}

_STATE_CODES: dict[int, str] = {
    1: "Alabama", 2: "Alaska", 3: "Arizona", 4: "Arkansas", 5: "California",
    6: "Colorado", 7: "Connecticut", 8: "Delaware", 9: "Florida", 10: "Georgia",
    11: "Hawaii", 12: "Idaho", 13: "Illinois", 14: "Indiana", 15: "Iowa",
    16: "Kansas", 17: "Kentucky", 18: "Louisiana", 19: "Maine", 20: "Maryland",
    21: "Massachusetts", 22: "Michigan", 23: "Minnesota", 24: "Mississippi",
    25: "Missouri", 26: "Montana", 27: "Nebraska", 28: "Nevada",
    29: "New Hampshire", 30: "New Jersey", 31: "New Mexico", 32: "New York",
    33: "North Carolina", 34: "North Dakota", 35: "Ohio", 36: "Oklahoma",
    37: "Oregon", 38: "Pennsylvania", 39: "Rhode Island", 40: "South Carolina",
    41: "South Dakota", 42: "Tennessee", 43: "Texas", 44: "Utah", 45: "Vermont",
    46: "Virginia", 47: "Washington", 48: "West Virginia", 49: "Wisconsin",
    50: "Wyoming", 51: "District of Columbia",
}


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
class VarData:
    """All fields from a TSYS VAR/Download Sheet — assembled from API data only."""
    # Merchant
    legal_name: str
    dba: str
    street: str
    city: str
    state: str
    zip_code: str
    phone: str
    mid: str
    mcc: str
    monthly_volume: float
    # Terminal
    v_number: str
    terminal_number: int       # tid
    store_number: str
    location_number: str
    chain: str
    agent_bank: str
    bin: str                   # derived from chain via _CHAIN_TO_BIN
    # Card types
    accept_visa_mc: bool
    accept_pin_debit: bool
    accept_gift_card: bool
    accept_amex: bool
    accept_discover: bool
    accept_ebt: bool

    def summary(self) -> str:
        def yn(b: bool) -> str: return "Yes" if b else "No"
        return (
            f"Legal Name:    {self.legal_name}\n"
            f"DBA:           {self.dba}\n"
            f"Address:       {self.street}, {self.city}, {self.state} {self.zip_code}\n"
            f"Phone:         {self.phone}\n"
            f"Merchant #:    {self.mid}\n"
            f"V Number:      {self.v_number}\n"
            f"MCC:           {self.mcc}\n"
            f"BIN:           {self.bin}\n"
            f"Chain:         {self.chain}\n"
            f"Agent Bank:    {self.agent_bank}\n"
            f"Terminal #:    {self.terminal_number}\n"
            f"Store #:       {self.store_number}\n"
            f"Location #:    {self.location_number}\n"
            f"Monthly Vol:   ${self.monthly_volume:,.2f}\n"
            f"Visa/MC:       {yn(self.accept_visa_mc)}\n"
            f"PIN Debit:     {yn(self.accept_pin_debit)}\n"
            f"Gift Card:     {yn(self.accept_gift_card)}\n"
            f"Amex:          {yn(self.accept_amex)}\n"
            f"Discover:      {yn(self.accept_discover)}\n"
            f"EBT:           {yn(self.accept_ebt)}"
        )

    def to_dict(self) -> dict:
        return {
            "legal_name": self.legal_name,
            "dba": self.dba,
            "street": self.street,
            "city": self.city,
            "state": self.state,
            "zip": self.zip_code,
            "phone": self.phone,
            "mid": self.mid,
            "mcc": self.mcc,
            "monthly_volume": self.monthly_volume,
            "v_number": self.v_number,
            "terminal_number": self.terminal_number,
            "store_number": self.store_number,
            "location_number": self.location_number,
            "chain": self.chain,
            "agent_bank": self.agent_bank,
            "bin": self.bin,
            "accept_visa_mc": self.accept_visa_mc,
            "accept_pin_debit": self.accept_pin_debit,
            "accept_gift_card": self.accept_gift_card,
            "accept_amex": self.accept_amex,
            "accept_discover": self.accept_discover,
            "accept_ebt": self.accept_ebt,
        }


# Reverse map: "California" → 5
_STATE_NAME_TO_ID: dict[str, int] = {v: k for k, v in _STATE_CODES.items()}


@dataclass(slots=True)
class OnboardingAddress:
    street: str
    city: str
    state: str  # full name, e.g. "California"
    zip: str
    country_id: int = 199  # USA


@dataclass(slots=True)
class OnboardingPrincipal:
    first_name: str
    last_name: str
    title: str  # "CEO" by default. Use "LLC Manager" for LLC, "President" if stated. Never use "Owner".
    ssn: str    # "XXX-XX-XXXX"
    dob: str    # "YYYY-MM-DD"
    email: str
    phone: str
    address: OnboardingAddress
    ownership_percentage: int = 100
    dl_number: str | None = None
    dl_expiration: str | None = None  # "YYYY-MM-DD"
    dl_state: str | None = None       # full state name
    nationality_id: int = 199         # USA


@dataclass(slots=True)
class NewMerchantProfile:
    # Business identity
    legal_name: str
    dba_name: str
    entity_type: str        # "LLC", "Corporation", "SoleProprietorship", "Partnership"
    ein: str                # federal tax ID, digits only
    founded_date: str       # "YYYY-MM-DD"
    mcc_id: int             # internal MCC ID (use MerchantOnboardingService.search_mcc())
    service_description: str
    # Addresses
    business_address: OnboardingAddress
    dba_same_as_company: bool = True
    # Contact
    business_phone: str = ""
    business_email: str = ""
    # Principals (at least one required)
    principals: list[OnboardingPrincipal] = field(default_factory=list)
    # Processing volumes
    monthly_volume: float = 50000.0
    avg_transaction: float = 50.0
    max_transaction: float = 500.0
    # Card types
    accept_credit: bool = True
    accept_pin_debit: bool = True
    accept_ebt: bool = False
    accept_amex: bool = True   # AMEX OptBlue is ON by default (KIT POS standard)
    # Business details
    refund_policy: str = "No refund policy"
    already_processing: bool = False
    has_been_terminated: bool = False
    has_bankruptcy: bool = False
    is_seasonal: bool = False
    inventory_on_site: bool = True
    # Banking (for processing account)
    routing_number: str = ""
    account_number: str = ""
    # API campaign (1579 = KIT POS InterCharge Plus)
    campaign_id: int = 1579


@dataclass(slots=True)
class OnboardingResult:
    app_id: int
    status: str
    message: str = ""
    url: str = ""
    validation_errors: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Application ID: {self.app_id}",
            f"Status:         {self.status}",
        ]
        if self.message:
            lines.append(f"Message:        {self.message}")
        if self.url:
            lines.append(f"URL:            {self.url}")
        if self.validation_errors:
            lines.append("Validation errors:")
            for k, v in self.validation_errors.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "app_id": self.app_id,
            "status": self.status,
            "message": self.message,
            "url": self.url,
            "validation_errors": self.validation_errors,
        }


@dataclass(slots=True)
class MerchantResult:
    merchant_id: str
    merchant_name: str
    profile_url: str
    principal_name: str
    phone: str
    email: str
    business_address: str = ""
    raw_fields: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Merchant:   {self.merchant_name}",
            f"ID:         {self.merchant_id}",
            f"Principal:  {self.principal_name or '(not found)'}",
            f"Phone:      {self.phone or '(not found)'}",
            f"Email:      {self.email or '(not found)'}",
            f"Address:    {self.business_address or '(not found)'}",
            f"Profile:    {self.profile_url}",
        ]
        return "\n".join(lines)
