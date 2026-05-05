from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import typer

from merchant_data.models import KitCredentials, NewMerchantProfile, OnboardingAddress, OnboardingPrincipal
from merchant_data.services.kit_merchant_lookup import MerchantLookupService
from merchant_data.services.kit_api import MerchantAPIService, UnknownChainError
from merchant_data.services.kit_var_downloader import VarDownloader
from merchant_data.services.kit_onboarding import MerchantOnboardingService, OnboardingAPIError
from merchant_data.services.kit_branding import MerchantBrandingService

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


# ──────────────────────── API VAR commands (no session, no browser) ──────────

def _print_var(var_list: list, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps([v.to_dict() for v in var_list], indent=2, ensure_ascii=False))
    else:
        for i, v in enumerate(var_list):
            if len(var_list) > 1:
                typer.echo(f"\n─── Terminal {i+1} of {len(var_list)} ───")
            typer.echo(v.summary())


def _handle_var_result(result, json_output: bool) -> None:
    """Print VAR results or guide the agent on unknown Chain."""
    _print_var(result, json_output)


def _handle_unknown_chain(exc: UnknownChainError) -> None:
    """Print a structured JSON block so any agent can parse and act on it."""
    chains = sorted(exc.chains)
    # Machine-readable block for agents
    payload = {
        "event": "UNKNOWN_CHAIN",
        "merchant_name": exc.merchant_name,
        "unknown_chains": chains,
        "action_required": (
            "1. Try VarDownloader (get-var-by-merchant-name) to download VAR PDF. "
            "2. If that fails, search Gmail: query='VAR available {merchant_name or MID}' "
            "   from:no-reply@kitdashboard.com. "
            "3. If VAR found via either method, extract BIN with pdfminer, "
            "   add to _CHAIN_TO_BIN in models.py, commit, retry. "
            "4. If nothing found, ask user to send the VAR file."
        ),
        "models_file": "src/merchant_data/models.py",
        "dict_name": "_CHAIN_TO_BIN",
    }
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False), err=True)


@app.command("api-var-by-mid")
def api_var_by_mid(
    mid: str = typer.Argument(..., help="12-digit MID, e.g. 201100300996"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[API] Get VAR sheet data by MID — pure API, no browser, no session."""
    service = _build_api_service(api_key)
    try:
        result = service.var_data_by_mid(mid)
    except UnknownChainError as exc:
        _handle_unknown_chain(exc)
        raise typer.Exit(2)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    _handle_var_result(result, json_output)


@app.command("api-var-by-name")
def api_var_by_name(
    name: str = typer.Argument(..., help="Merchant name or partial name"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[API] Get VAR sheet data by merchant name — pure API, no browser, no session."""
    service = _build_api_service(api_key)
    try:
        result = service.var_data_by_name(name)
    except UnknownChainError as exc:
        _handle_unknown_chain(exc)
        raise typer.Exit(2)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    _handle_var_result(result, json_output)


# ─────────────────────── Boarding Application commands ───────────────────────

def _build_onboarding_service(api_key: str | None) -> MerchantOnboardingService:
    key = api_key or os.environ.get("KIT_API_KEY", "")
    if not key:
        typer.echo("ERROR: Provide --api-key or set KIT_API_KEY in .env", err=True)
        raise typer.Exit(1)
    return MerchantOnboardingService(key)


@app.command("board-list")
def board_list(
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    limit: int = typer.Option(20, "--limit", help="Max applications to return"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status (New, Approved, etc.)"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[API] List boarding applications, newest first."""
    service = _build_onboarding_service(api_key)
    try:
        apps = service.list_applications(limit=limit, status=status)
    except OnboardingAPIError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(apps, indent=2, ensure_ascii=False))
    else:
        for app in apps:
            co = app.get("company", {}).get("name", "(unnamed)")
            typer.echo(
                f"  ID {app['id']:>7}  {app['status']:<12}  {co}  "
                f"({app.get('updatedOn', '')[:10]})"
            )


@app.command("board-get")
def board_get(
    app_id: int = typer.Argument(..., help="Boarding application ID"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[API] Get full details of a boarding application."""
    service = _build_onboarding_service(api_key)
    try:
        data = service.get_application(app_id)
    except OnboardingAPIError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        co = data.get("company", {})
        dba = data.get("dba", {})
        typer.echo(f"ID:            {data.get('id')}")
        typer.echo(f"Status:        {data.get('status')}")
        typer.echo(f"Legal Name:    {co.get('name')}")
        typer.echo(f"DBA:           {dba.get('name')}")
        typer.echo(f"Entity Type:   {co.get('type')}")
        typer.echo(f"EIN:           {co.get('federalTaxId')}")
        addr = co.get("address", {})
        typer.echo(f"Address:       {addr.get('street')}, {addr.get('city')} {addr.get('zip')}")
        typer.echo(f"Created:       {data.get('createdOn')}")
        typer.echo(f"Updated:       {data.get('updatedOn')}")


@app.command("board-validate")
def board_validate(
    app_id: int = typer.Argument(..., help="Boarding application ID"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[API] Validate a boarding application and show missing/invalid fields."""
    service = _build_onboarding_service(api_key)
    try:
        errors = service.validate_application(app_id)
    except OnboardingAPIError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(errors, indent=2, ensure_ascii=False))
    elif errors:
        typer.echo(f"Validation errors ({len(errors)}):")
        for field, msg in errors.items():
            typer.echo(f"  {field}: {msg}")
    else:
        typer.echo("✓ Application is valid — no errors found.")


@app.command("board-mcc-search")
def board_mcc_search(
    query: str = typer.Argument(..., help="MCC code (e.g. '5411') or description keyword (e.g. 'grocery')"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[API] Search MCC codes by number or description. Use the id field in board-create."""
    service = _build_onboarding_service(api_key)
    try:
        results = service.search_mcc(query)
    except OnboardingAPIError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(results, indent=2, ensure_ascii=False))
    elif results:
        for item in results:
            typer.echo(f"  id={item['id']:<6}  code={item['number']}  {item['description']}")
    else:
        typer.echo(f"No MCC found matching {query!r}.")


@app.command("board-create")
def board_create(
    legal_name: str = typer.Option(..., "--legal-name", help="Legal / corporate name"),
    dba: str = typer.Option(..., "--dba", help="DBA (doing business as) name"),
    entity_type: str = typer.Option(..., "--entity-type", help="LLC | Corporation | SoleProprietorship | Partnership"),
    ein: str = typer.Option(..., "--ein", help="Federal Tax ID / EIN (digits only)"),
    founded: str = typer.Option(..., "--founded", help="Date founded YYYY-MM-DD"),
    mcc_id: int = typer.Option(..., "--mcc-id", help="MCC internal ID (find with board-mcc-search)"),
    description: str = typer.Option(..., "--description", help="Short business description"),
    street: str = typer.Option(..., "--street"),
    city: str = typer.Option(..., "--city"),
    state: str = typer.Option(..., "--state", help="Full state name, e.g. 'California'"),
    zip_code: str = typer.Option(..., "--zip"),
    phone: str = typer.Option(..., "--phone", help="Business phone, e.g. +1 310-555-0100"),
    email: str = typer.Option(..., "--email", help="Business email"),
    # Principal
    p_first: str = typer.Option(..., "--principal-first", help="Principal first name"),
    p_last: str = typer.Option(..., "--principal-last", help="Principal last name"),
    p_title: str = typer.Option("Owner", "--principal-title"),
    p_ssn: str = typer.Option(..., "--principal-ssn", help="SSN: XXX-XX-XXXX"),
    p_dob: str = typer.Option(..., "--principal-dob", help="Date of birth YYYY-MM-DD"),
    p_email: str = typer.Option(..., "--principal-email"),
    p_phone: str = typer.Option(..., "--principal-phone"),
    p_street: str = typer.Option(..., "--principal-street"),
    p_city: str = typer.Option(..., "--principal-city"),
    p_state: str = typer.Option(..., "--principal-state", help="Full state name"),
    p_zip: str = typer.Option(..., "--principal-zip"),
    # Processing
    monthly_volume: float = typer.Option(50000.0, "--monthly-volume"),
    avg_tx: float = typer.Option(50.0, "--avg-tx"),
    max_tx: float = typer.Option(500.0, "--max-tx"),
    routing: str = typer.Option("", "--routing", help="Bank routing number"),
    account: str = typer.Option("", "--account", help="Bank account number"),
    accept_ebt: bool = typer.Option(False, "--ebt/--no-ebt"),
    campaign_id: int = typer.Option(1579, "--campaign-id", help="KIT campaign ID (default 1579)"),
    # Output
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """[API] Create a new boarding application with full merchant profile.

    Use board-mcc-search to find the correct mcc_id before running this.
    After creation, use board-validate to check for remaining errors.
    """
    service = _build_onboarding_service(api_key)
    biz_addr = OnboardingAddress(street=street, city=city, state=state, zip=zip_code)
    principal = OnboardingPrincipal(
        first_name=p_first, last_name=p_last, title=p_title,
        ssn=p_ssn, dob=p_dob, email=p_email, phone=p_phone,
        address=OnboardingAddress(street=p_street, city=p_city, state=p_state, zip=p_zip),
    )
    profile = NewMerchantProfile(
        legal_name=legal_name,
        dba_name=dba,
        entity_type=entity_type,
        ein=ein,
        founded_date=founded,
        mcc_id=mcc_id,
        service_description=description,
        business_address=biz_addr,
        business_phone=phone,
        business_email=email,
        principals=[principal],
        monthly_volume=monthly_volume,
        avg_transaction=avg_tx,
        max_transaction=max_tx,
        routing_number=routing,
        account_number=account,
        accept_ebt=accept_ebt,
        campaign_id=campaign_id,
    )
    try:
        result = service.create_application(profile)
    except OnboardingAPIError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        typer.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        typer.echo(result.summary())


# ─────────────────────────── Branding / Logo commands ───────────────────────

def _build_branding_service(api_key: str | None, email: str | None, password: str | None, verification_code: str | None) -> MerchantBrandingService:
    key = api_key or os.environ.get("KIT_API_KEY", "")
    if not key:
        typer.echo("ERROR: Provide --api-key or set KIT_API_KEY in .env", err=True)
        raise typer.Exit(1)
    creds = _build_credentials(email, password, verification_code)
    return MerchantBrandingService(key, creds)


@app.command("upload-logo")
def upload_logo(
    image: Path = typer.Argument(..., help="Path to logo image (JPEG, PNG, or GIF)"),
    name: Optional[str] = typer.Option(None, "--name", help="Merchant name (partial match)"),
    mid: Optional[str] = typer.Option(None, "--mid", help="12-digit KIT Merchant ID"),
    internal_id: Optional[int] = typer.Option(None, "--internal-id", help="Dashboard internal id (from profile URL ?id=XXXXX)"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
) -> None:
    """[Session] Upload a logo image for an active merchant.

    Identify the merchant with one of: --name, --mid, or --internal-id.

    Examples:
      merchant upload-logo logo.png --name "Snack Zone"
      merchant upload-logo logo.png --mid 201100306415
      merchant upload-logo logo.png --internal-id 303608
    """
    if not any([name, mid, internal_id]):
        typer.echo("ERROR: Provide one of: --name, --mid, or --internal-id", err=True)
        raise typer.Exit(1)

    service = _build_branding_service(api_key, email, password, verification_code)
    try:
        if internal_id is not None:
            result = service.upload_logo_by_internal_id(internal_id, image)
        elif mid:
            result = service.upload_logo_by_mid(mid, image)
        else:
            result = service.upload_logo_by_name(name, image)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(result.summary())


@app.command("remove-logo")
def remove_logo(
    name: Optional[str] = typer.Option(None, "--name", help="Merchant name (partial match)"),
    internal_id: Optional[int] = typer.Option(None, "--internal-id", help="Dashboard internal id"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
) -> None:
    """[Session] Remove the logo for an active merchant.

    Examples:
      merchant remove-logo --name "Snack Zone"
      merchant remove-logo --internal-id 303608
    """
    if not any([name, internal_id]):
        typer.echo("ERROR: Provide one of: --name or --internal-id", err=True)
        raise typer.Exit(1)

    service = _build_branding_service(api_key, email, password, verification_code)
    try:
        if internal_id is not None:
            result = service.remove_logo_by_internal_id(internal_id)
        else:
            result = service.remove_logo_by_name(name)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(result.summary())


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


@app.command("get-var-by-mid")
def get_var_by_mid(
    mid: str = typer.Argument(..., help="12-digit KIT Merchant ID, e.g. 201100300996"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
    headless: bool = typer.Option(True),
    save_dir: Path = typer.Option(Path("downloads"), "--save-dir"),
) -> None:
    """[API+Session] Download VAR PDF by MID — API finds terminal, session downloads PDF."""
    creds = _build_credentials(email, password, verification_code)
    service = VarDownloader(_build_api_service(api_key).api_key, creds, headless=headless)
    try:
        result = service.download_by_mid(mid, save_dir)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(result.summary())


@app.command("get-var-by-merchant-name")
def get_var_by_merchant_name(
    name: str = typer.Argument(..., help="Merchant name, e.g. 'El Camino'"),
    api_key: Optional[str] = typer.Option(None, envvar="KIT_API_KEY"),
    email: Optional[str] = typer.Option(None, envvar="KIT_EMAIL"),
    password: Optional[str] = typer.Option(None, envvar="KIT_PASSWORD"),
    verification_code: Optional[str] = typer.Option(None, "--verification-code"),
    headless: bool = typer.Option(True),
    save_dir: Path = typer.Option(Path("downloads"), "--save-dir"),
) -> None:
    """[API+Session] Download VAR PDF by merchant name — API finds terminal, session downloads PDF."""
    creds = _build_credentials(email, password, verification_code)
    service = VarDownloader(_build_api_service(api_key).api_key, creds, headless=headless)
    try:
        result = service.download_by_name(name, save_dir)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(result.summary())


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
