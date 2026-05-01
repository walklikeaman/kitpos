from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(slots=True)
class Settings:
    paxstore_base_url: str | None
    paxstore_api_key: str | None
    paxstore_api_secret: str | None
    paxstore_time_zone: str
    mail_provider: str | None
    mail_imap_host: str | None
    mail_imap_port: int
    mail_imap_mailbox: str
    mail_username: str | None
    mail_password: str | None
    mail_scan_limit: int
    llm_provider: str
    openrouter_api_key: str | None
    openrouter_base_url: str
    openrouter_model: str
    kit_dashboard_url: str
    kit_dashboard_email: str | None
    kit_dashboard_password: str | None
    kit_dashboard_storage_state: str
    kit_api_key: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            paxstore_base_url=os.getenv("PAXSTORE_BASE_URL"),
            paxstore_api_key=os.getenv("PAXSTORE_API_KEY"),
            paxstore_api_secret=os.getenv("PAXSTORE_API_SECRET"),
            paxstore_time_zone=os.getenv("PAXSTORE_TIME_ZONE", "UTC"),
            mail_provider=os.getenv("MAIL_PROVIDER"),
            mail_imap_host=os.getenv("MAIL_IMAP_HOST"),
            mail_imap_port=int(os.getenv("MAIL_IMAP_PORT", "993")),
            mail_imap_mailbox=os.getenv("MAIL_IMAP_MAILBOX", "INBOX"),
            mail_username=os.getenv("MAIL_USERNAME"),
            mail_password=os.getenv("MAIL_PASSWORD"),
            mail_scan_limit=int(os.getenv("MAIL_SCAN_LIMIT", "50")),
            llm_provider=os.getenv("LLM_PROVIDER", "openrouter"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "openrouter/free"),
            kit_dashboard_url=os.getenv("KIT_DASHBOARD_URL", "https://kitdashboard.com/"),
            kit_dashboard_email=os.getenv("KIT_DASHBOARD_EMAIL") or os.getenv("KIT_EMAIL"),
            kit_dashboard_password=os.getenv("KIT_DASHBOARD_PASSWORD") or os.getenv("KIT_PASSWORD"),
            kit_dashboard_storage_state=os.getenv("KIT_DASHBOARD_STORAGE_STATE", "tmp/kit-dashboard-state.json"),
            kit_api_key=os.getenv("KIT_API_KEY"),
        )
