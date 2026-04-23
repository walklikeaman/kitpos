from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
import typer

from maverick_agent.config import Settings
from maverick_agent.models import MerchantRequest
from maverick_agent.orchestrator import ProvisioningOrchestrator
from maverick_agent.parsers.var_pdf import VarPdfParser
from maverick_agent.services.inbox import ImapInboxClient


app = typer.Typer(no_args_is_help=True, help="Maverick Terminal Agent - Terminal provisioning automation.")


def _build_orchestrator(settings: Settings) -> ProvisioningOrchestrator:
    inbox_client = None
    if (
        settings.mail_provider == "imap"
        and settings.mail_imap_host
        and settings.mail_username
        and settings.mail_password
    ):
        inbox_client = ImapInboxClient(
            host=settings.mail_imap_host,
            port=settings.mail_imap_port,
            username=settings.mail_username,
            password=settings.mail_password,
            mailbox=settings.mail_imap_mailbox,
            scan_limit=settings.mail_scan_limit,
        )
    return ProvisioningOrchestrator(parser=VarPdfParser(), inbox_client=inbox_client)


@app.callback()
def main() -> None:
    load_dotenv()


@app.command("parse-pdf")
def parse_pdf(pdf_path: Path) -> None:
    """Parse a VAR PDF and extract field values."""
    payload = VarPdfParser().parse_file(pdf_path)
    typer.echo(json.dumps(payload.to_dict(), indent=2, ensure_ascii=True))


@app.command("plan")
def plan(
    merchant_id: str = typer.Option(..., help="Merchant ID received from the operator."),
    serial_number: str = typer.Option(..., help="Terminal or pinpad serial number."),
    pdf: Path | None = typer.Option(None, help="Optional direct path to the merchant PDF."),
) -> None:
    """Build a provisioning plan for adding a terminal to a merchant."""
    settings = Settings.from_env()
    orchestrator = _build_orchestrator(settings)
    request = MerchantRequest(
        merchant_id=merchant_id,
        serial_number=serial_number,
        pdf_path=pdf,
    )
    outcome = orchestrator.build_plan(request)
    typer.echo(json.dumps(outcome.to_dict(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    app()
