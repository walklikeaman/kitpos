from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import typer

from merchant_data.models import KitCredentials
from merchant_data.services.kit_merchant_lookup import MerchantLookupService

app = typer.Typer(no_args_is_help=True, help="KIT Dashboard – merchant lookup by ID or name.")


@app.callback()
def main() -> None:
    load_dotenv()


def _build_credentials(
    email: str | None,
    password: str | None,
    verification_code: str | None,
) -> KitCredentials:
    email = email or os.environ.get("KIT_EMAIL", "")
    password = password or os.environ.get("KIT_PASSWORD", "")
    if not email or not password:
        typer.echo("ERROR: Provide --email/--password or set KIT_EMAIL/KIT_PASSWORD in .env", err=True)
        raise typer.Exit(1)
    return KitCredentials(email=email, password=password, verification_code=verification_code)


@app.command("by-id")
def lookup_by_id(
    merchant_id: str = typer.Argument(..., help="Merchant ID, e.g. 201100300996"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL", help="KIT Dashboard email"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD", help="KIT Dashboard password"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code", help="2FA code if required"),
    headless: bool = typer.Option(True, help="Run browser in headless mode"),
    debug: bool = typer.Option(False, help="Save screenshots and page text to ./debug/"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of human-readable text"),
) -> None:
    """Look up a merchant by their KIT Merchant ID and print principal name + phone."""
    creds = _build_credentials(email, password, verification_code)
    debug_dir = Path("debug") if debug else None
    service = MerchantLookupService(creds, headless=headless, debug_dir=debug_dir)

    try:
        result = asyncio.run(service.lookup_by_id(merchant_id))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        data = {
            "merchant_id": result.merchant_id,
            "merchant_name": result.merchant_name,
            "profile_url": result.profile_url,
            "principal_name": result.principal_name,
            "phone": result.phone,
            "email": result.email,
        }
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        typer.echo(result.summary())


@app.command("by-name")
def lookup_by_name(
    name: str = typer.Argument(..., help="Merchant name or partial name, e.g. 'El Camino'"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL", help="KIT Dashboard email"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD", help="KIT Dashboard password"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code", help="2FA code if required"),
    headless: bool = typer.Option(True, help="Run browser in headless mode"),
    debug: bool = typer.Option(False, help="Save screenshots and page text to ./debug/"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of human-readable text"),
) -> None:
    """Look up a merchant by name and print principal name + phone."""
    creds = _build_credentials(email, password, verification_code)
    debug_dir = Path("debug") if debug else None
    service = MerchantLookupService(creds, headless=headless, debug_dir=debug_dir)

    try:
        result = asyncio.run(service.lookup_by_name(name))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        data = {
            "merchant_id": result.merchant_id,
            "merchant_name": result.merchant_name,
            "profile_url": result.profile_url,
            "principal_name": result.principal_name,
            "phone": result.phone,
            "email": result.email,
        }
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        typer.echo(result.summary())


@app.command("get-var-by-id")
def get_var_by_id(
    merchant_id: str = typer.Argument(..., help="Merchant ID, e.g. 201100300996"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
    headless: bool = typer.Option(True),
    save_dir: Path = typer.Option(Path("downloads"), "--save-dir", help="Directory to save the VAR file"),
    debug: bool = typer.Option(False, help="Save screenshots to ./debug/"),
) -> None:
    """Download the VAR file for a merchant found by their KIT Merchant ID."""
    creds = _build_credentials(email, password, verification_code)
    debug_dir = Path("debug") if debug else None
    service = MerchantLookupService(creds, headless=headless, debug_dir=debug_dir)

    try:
        result = asyncio.run(service.download_var_by_id(merchant_id, save_dir))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(result.summary())


@app.command("get-var-by-name")
def get_var_by_name(
    name: str = typer.Argument(..., help="Merchant name, e.g. 'El Camino'"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
    headless: bool = typer.Option(True),
    save_dir: Path = typer.Option(Path("downloads"), "--save-dir", help="Directory to save the VAR file"),
    debug: bool = typer.Option(False, help="Save screenshots to ./debug/"),
) -> None:
    """Download the VAR file for a merchant found by name."""
    creds = _build_credentials(email, password, verification_code)
    debug_dir = Path("debug") if debug else None
    service = MerchantLookupService(creds, headless=headless, debug_dir=debug_dir)

    try:
        result = asyncio.run(service.download_var_by_name(name, save_dir))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(result.summary())


if __name__ == "__main__":
    app()
