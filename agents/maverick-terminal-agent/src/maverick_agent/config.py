from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(slots=True)
class Settings:
    # PAX Store REST API (future — not yet used by browser workflow)
    paxstore_base_url: str | None
    paxstore_api_key: str | None
    paxstore_api_secret: str | None

    # Email inbox — last-resort fallback for VAR PDF retrieval
    mail_provider: str | None
    mail_imap_host: str | None
    mail_imap_port: int
    mail_imap_mailbox: str
    mail_username: str | None
    mail_password: str | None
    mail_scan_limit: int

    # KIT Dashboard API — primary VAR data source
    kit_api_key: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            paxstore_base_url=os.getenv("PAXSTORE_BASE_URL"),
            paxstore_api_key=os.getenv("PAXSTORE_API_KEY"),
            paxstore_api_secret=os.getenv("PAXSTORE_API_SECRET"),
            mail_provider=os.getenv("MAIL_PROVIDER"),
            mail_imap_host=os.getenv("MAIL_IMAP_HOST"),
            mail_imap_port=int(os.getenv("MAIL_IMAP_PORT", "993")),
            mail_imap_mailbox=os.getenv("MAIL_IMAP_MAILBOX", "INBOX"),
            mail_username=os.getenv("MAIL_USERNAME"),
            mail_password=os.getenv("MAIL_PASSWORD"),
            mail_scan_limit=int(os.getenv("MAIL_SCAN_LIMIT", "50")),
            kit_api_key=os.getenv("KIT_API_KEY"),
        )
