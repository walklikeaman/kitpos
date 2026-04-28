from __future__ import annotations
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Amazon SP-API credentials
    sp_api_client_id: str = field(default_factory=lambda: os.getenv("SP_API_CLIENT_ID", ""))
    sp_api_client_secret: str = field(default_factory=lambda: os.getenv("SP_API_CLIENT_SECRET", ""))
    sp_api_refresh_token: str = field(default_factory=lambda: os.getenv("SP_API_REFRESH_TOKEN", ""))
    sp_api_marketplace_id: str = field(default_factory=lambda: os.getenv("SP_API_MARKETPLACE_ID", "ATVPDKIKX0DER"))  # US

    # Amazon Business account
    amazon_business_email: str = field(default_factory=lambda: os.getenv("AMAZON_BUSINESS_EMAIL", ""))

    # Claude API
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    # Agent rules
    max_delivery_business_days: int = 4
    min_match_confidence: float = 0.75  # below this → show candidates

    # Trusted sellers (besides Amazon itself)
    trusted_sellers: list[str] = field(default_factory=lambda: [
        "Amazon.com",
        "Amazon Business",
        "Sold by Amazon",
    ])

    # Products that have been bought before — bypass confirmation
    allowlist_asins: list[str] = field(default_factory=list)

    # Pinned ASINs: when a query keyword matches a key, always use the pinned ASIN.
    # Prevents accidentally buying the wrong variant (e.g. USB Ethernet vs USB+BT).
    # Key = lowercase keyword fragment, Value = (asin, human label)
    pinned_asins: dict[str, tuple[str, str]] = field(default_factory=lambda: {
        # Volcora printer — always black USB+Bluetooth, never USB Ethernet
        "volcora": ("B09GCR1VYL", "Volcora Thermal Receipt Printer 80mm USB+Bluetooth Black"),
        "volcora thermal": ("B09GCR1VYL", "Volcora Thermal Receipt Printer 80mm USB+Bluetooth Black"),
        "thermal receipt printer": ("B09GCR1VYL", "Volcora Thermal Receipt Printer 80mm USB+Bluetooth Black"),
        # PIN Pad / PAX stand — Hilipro Swivel Stand for Pax A35 (confirmed from Buy Again recording)
        "pax stand": ("B0BMB9T82D", "Hilipro Swivel Stand for Pax A35 / PIN Pad Stand"),
        "pin pad stand": ("B0BMB9T82D", "Hilipro Swivel Stand for Pax A35 / PIN Pad Stand"),
        "terminal stand": ("B0BMB9T82D", "Hilipro Swivel Stand for Pax A35 / PIN Pad Stand"),
        "pax a35 stand": ("B0BMB9T82D", "Hilipro Swivel Stand for Pax A35 / PIN Pad Stand"),
        "hilipro": ("B0BMB9T82D", "Hilipro Swivel Stand for Pax A35 / PIN Pad Stand"),
    })

    # Webhook auth token
    webhook_secret: str = field(default_factory=lambda: os.getenv("WEBHOOK_SECRET", "change-me"))


config = Config()
