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
from merchant_data.services.kit_api import MerchantAPIService

app = typer.Typer(no_args_is_help=True, help="KIT Dashboard – merchant lookup by ID or name.")


@app.callback()
def main() -> None:
    load_dotenv()


# ─────────────────────────────── helpers ─────────────────────────────────────

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


def _build_api_service(api_key: str | None) -> MerchantAPIService:
    key = api_key or os.environ.get("KIT_API_KEY", "")
    if not key:
        typer.echo("ERROR: Provide --api-key or set KIT_API_KEY in .env", err=True)
        raise typer.Exit(1)
    return MerchantAPIService(key)


def _print_result(result, json_output: bool) -> None:
    if json_output:
        data = {
            "merchant_id": result.merchant_id,
            "merchant_name": result.merchant_name,
            "profile_url": result.profile_url,
            "principal_name": result.principal_name,
            "phone": result.phone,
            "email": result.email,
            "business_address": result.business_address,
        }
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        typer.echo(result.summary())


# ─────────────────────────── API commands (fast, no browser) ─────────────────

@app.command("api-by-name")
def api_by_name(
    name: str = typer.Argument(..., help="Merchant name or partial name, e.g. 'El Camino'"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY", help="Maverick Payments API key"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """[API] Look up a merchant by name — instant, no browser needed."""
    service = _build_api_service(api_key)
    try:
        result = service.lookup_by_name(name)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    _print_result(result, json_output)


@app.command("api-by-mid")
def api_by_mid(
    mid: str = typer.Argument(..., help="12-digit KIT Merchant ID, e.g. 201100300996"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY", help="Maverick Payments API key"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """[API] Look up a merchant by MID — scans all merchants via API, no browser."""
    service = _build_api_service(api_key)
    try:
        result = service.lookup_by_mid(mid)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    _print_result(result, json_output)


@app.command("api-by-internal-id")
def api_by_internal_id(
    internal_id: int = typer.Argument(..., help="Internal API ID (from profile URL ?id=XXXXX)"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY", help="Maverick Payments API key"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """[API] Look up a merchant by internal dashboard ID — single call, fastest."""
    service = _build_api_service(api_key)
    try:
        result = service.lookup_by_internal_id(internal_id)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    _print_result(result, json_output)


# ──────────────────────── Browser commands (kept for VAR download) ────────────

@app.command("by-id")
def lookup_by_id(
    merchant_id: str = typer.Argument(..., help="Merchant ID, e.g. 201100300996"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
    headless: bool = typer.Option(True),
    debug: bool = typer.Option(False, help="Save screenshots to ./debug/"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[Browser] Look up a merchant by KIT MID (legacy browser approach)."""
    creds = _build_credentials(email, password, verification_code)
    service = MerchantLookupService(creds, headless=headless, debug_dir=Path("debug") if debug else None)
    try:
        result = asyncio.run(service.lookup_by_id(merchant_id))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    _print_result(result, json_output)


@app.command("by-name")
def lookup_by_name(
    name: str = typer.Argument(..., help="Merchant name or partial name"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
    headless: bool = typer.Option(True),
    debug: bool = typer.Option(False, help="Save screenshots to ./debug/"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[Browser] Look up a merchant by name (legacy browser approach)."""
    creds = _build_credentials(email, password, verification_code)
    service = MerchantLookupService(creds, headless=headless, debug_dir=Path("debug") if debug else None)
    try:
        result = asyncio.run(service.lookup_by_name(name))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    _print_result(result, json_output)


@app.command("get-var-by-id")
def get_var_by_id(
    merchant_id: str = typer.Argument(..., help="Merchant ID, e.g. 201100300996"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
    headless: bool = typer.Option(True),
    save_dir: Path = typer.Option(Path("downloads"), "--save-dir"),
    debug: bool = typer.Option(False),
) -> None:
    """[Browser] Download the VAR PDF by KIT Merchant ID."""
    creds = _build_credentials(email, password, verification_code)
    service = MerchantLookupService(creds, headless=headless, debug_dir=Path("debug") if debug else None)
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
    save_dir: Path = typer.Option(Path("downloads"), "--save-dir"),
    debug: bool = typer.Option(False),
) -> None:
    """[Browser] Download the VAR PDF by merchant name."""
    creds = _build_credentials(email, password, verification_code)
    service = MerchantLookupService(creds, headless=headless, debug_dir=Path("debug") if debug else None)
    try:
        result = asyncio.run(service.download_var_by_name(name, save_dir))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(result.summary())


if __name__ == "__main__":
    app()
