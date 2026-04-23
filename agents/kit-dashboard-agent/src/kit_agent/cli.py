from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
import typer

from kit_agent.kit_orchestrator import KitMerchantOnboardingOrchestrator, format_kit_onboarding_report
from kit_agent.parsers.kit_documents import KitDocumentParser


app = typer.Typer(no_args_is_help=True, help="KIT Dashboard Agent - Merchant onboarding automation.")


@app.callback()
def main() -> None:
    load_dotenv()


@app.command("parse-docs")
def kit_parse_docs(
    documents: list[Path] = typer.Argument(..., help="Application, driver-license, and bank/voided-check documents."),
    reveal_sensitive: bool = typer.Option(False, help="Print raw SSN/EIN/account values in JSON output."),
) -> None:
    """Parse merchant documents and extract profile data."""
    payload = KitDocumentParser().parse_files(documents)
    typer.echo(json.dumps(payload.to_dict(mask_sensitive=not reveal_sensitive), indent=2, ensure_ascii=True))


@app.command("plan")
def kit_plan(
    documents: list[Path] = typer.Argument(..., help="Application, driver-license, and bank/voided-check documents."),
    reveal_sensitive: bool = typer.Option(False, help="Print raw SSN/EIN/account values in JSON output."),
) -> None:
    """Build an onboarding plan from merchant documents."""
    orchestrator = KitMerchantOnboardingOrchestrator(parser=KitDocumentParser())
    outcome = orchestrator.build_plan(documents)
    typer.echo(json.dumps(outcome.to_dict(mask_sensitive=not reveal_sensitive), indent=2, ensure_ascii=True))


@app.command("report")
def kit_report(
    documents: list[Path] = typer.Argument(..., help="Application, driver-license, and bank/voided-check documents."),
) -> None:
    """Generate a formatted onboarding report."""
    orchestrator = KitMerchantOnboardingOrchestrator(parser=KitDocumentParser())
    outcome = orchestrator.build_plan(documents)
    typer.echo(format_kit_onboarding_report(outcome))


if __name__ == "__main__":
    app()
