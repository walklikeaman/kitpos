from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from datetime import UTC
import json
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
import sys

from dotenv import load_dotenv
from playwright.async_api import Locator
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from maverick_agent.parsers.var_pdf import VarPdfParser
from maverick_agent.config import Settings
from maverick_agent.services.inbox import ImapInboxClient


LOGIN_URL = "https://auth.paxstore.us/passport/login?client_id=admin&market=paxus"
SCREENSHOT_DIR = Path("tmp/screenshots")
RUN_HISTORY_DIR = Path("tmp/run-history")
RUN_HISTORY_FILE = RUN_HISTORY_DIR / "paxstore_runs.jsonl"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
KIT_DASHBOARD_AGENT_DIR = REPO_ROOT / "agents" / "kit-dashboard-merchant-data"
DEFAULT_VAR_DOWNLOAD_DIR = PROJECT_ROOT / "downloads"
PINPAD_MODELS_WITH_BACK_SCREEN = {"A3700", "3700"}


@dataclass(slots=True)
class PaxProvisioningData:
    dba_name: str
    merchant_number: str
    serial_number: str
    merchant_display_name: str
    terminal_display_name: str
    bin: str
    agent_bank: str
    chain: str
    store_number: str
    terminal_number: str
    city: str
    state: str
    zip: str
    mcc: str
    terminal_id_number: str
    timezone_query: str = "pst"
    timezone_option: str = "708-PST"

    @classmethod
    def from_pdf(
        cls,
        pdf_path: Path,
        serial_number: str,
        merchant_number_override: str | None = None,
    ) -> "PaxProvisioningData":
        payload = VarPdfParser().parse_file(pdf_path)
        if payload.missing_required:
            raise RuntimeError(f"PDF is missing required fields: {', '.join(payload.missing_required)}")

        fields = payload.fields
        merchant_number = merchant_number_override or fields["merchant_number"]
        dba_name = fields["dba_name"]
        return cls(
            dba_name=dba_name,
            merchant_number=merchant_number,
            serial_number=serial_number,
            merchant_display_name=f"{dba_name} {merchant_number}",
            terminal_display_name=f"{dba_name} {serial_number}",
            bin=fields["bin"],
            agent_bank=fields["agent_bank"],
            chain=fields["chain"],
            store_number=fields["store_number"],
            terminal_number=fields["terminal_number"],
            city=fields.get("city", ""),
            state=fields.get("state", ""),
            zip=fields.get("zip", ""),
            mcc=fields.get("mcc", ""),
            terminal_id_number=fields["terminal_id_number"],
        )


@dataclass(slots=True)
class TerminalDevice:
    role: str
    serial_number: str
    expected_model: str | None = None
    install_back_screen: bool | None = None

    def display_name(self, data: PaxProvisioningData) -> str:
        return f"{data.dba_name} {self.serial_number}"

    def needs_back_screen(self) -> bool:
        if self.install_back_screen is not None:
            return self.install_back_screen
        model = (self.expected_model or "").upper().replace("PAX", "").strip()
        return model in PINPAD_MODELS_WITH_BACK_SCREEN


async def snapshot(page: Page, name: str) -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=SCREENSHOT_DIR / f"{name}.png", full_page=True)
    text = await page.locator("body").inner_text(timeout=8000)
    (SCREENSHOT_DIR / f"{name}.txt").write_text(text[:24000], encoding="utf-8")
    print(f"\n--- {name} ---")
    print(f"URL: {page.url}")
    print(text[:6000])
    return text


async def click_if_visible(page: Page, selector: str) -> bool:
    locator = page.locator(selector).first
    try:
        if await locator.is_visible(timeout=1200):
            await locator.click()
            return True
    except PlaywrightTimeoutError:
        return False
    return False


async def fill_first_visible(page: Page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.is_visible(timeout=1500):
                await locator.fill(value)
                return True
        except PlaywrightTimeoutError:
            continue
    return False


async def click_button_by_text_or_label(page: Page, label: str) -> None:
    clicked = await page.evaluate(
        """(label) => {
            const buttons = Array.from(document.querySelectorAll('button, [role="button"], li'));
            const normalized = (value) => (value || '').replace(/\\s+/g, ' ').trim();
            const item = buttons.find((el) => {
                const haystack = [
                    el.innerText,
                    el.getAttribute('aria-label'),
                    el.getAttribute('title'),
                    el.id
                ].map(normalized).filter(Boolean).join(' ');
                return haystack.includes(label);
            });
            if (!item) return false;
            item.click();
            return true;
        }""",
        label,
    )
    if not clicked:
        raise RuntimeError(f"Could not click item: {label}")


async def click_button_or_text(page: Page, label: str) -> None:
    locators = (
        page.get_by_role("button", name=label).first,
        page.get_by_role("tab", name=label).first,
        page.get_by_text(label, exact=True).first,
        page.get_by_text(label, exact=False).first,
    )
    for locator in locators:
        try:
            if await locator.is_visible(timeout=1500):
                await locator.click()
                return
        except PlaywrightTimeoutError:
            continue
    await click_button_by_text_or_label(page, label)


async def select_first_result_row(page: Page) -> None:
    selected = await page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]')).filter(visible);
            if (checkboxes.length) {
                checkboxes[0].click();
                return 'checkbox';
            }
            const rows = Array.from(document.querySelectorAll('tbody tr, .el-table__row, tr')).filter((row) => {
                const text = (row.innerText || '').trim();
                return text
                    && visible(row)
                    && !/No data found/i.test(text)
                    && !/Firmware Name\\s+Size\\s+Force Update/i.test(text)
                    && !/App Name\\s+Version/i.test(text);
            });
            if (rows.length) {
                const preferred = rows.find((row) => /Uniphiz_|KIT\\s|BroadPOS|TSYS|Sierra/i.test(row.innerText || '')) || rows[0];
                preferred.scrollIntoView({block: 'center', inline: 'center'});
                const rect = preferred.getBoundingClientRect();
                const x = rect.left + 20;
                const y = rect.top + rect.height / 2;
                const clickable = document.elementFromPoint(x, y)
                    || preferred.querySelector('td:first-child, label, span')
                    || preferred;
                for (const type of ['mouseover', 'mousedown', 'mouseup', 'click']) {
                    clickable.dispatchEvent(new MouseEvent(type, {
                        bubbles: true,
                        cancelable: true,
                        clientX: x,
                        clientY: y,
                        view: window,
                    }));
                }
                return 'row';
            }
            return null;
        }"""
    )
    if not selected:
        raise RuntimeError("Could not select the first result row")


async def ensure_checkbox_by_label(page: Page, label_text: str) -> None:
    checked = await page.evaluate(
        """(labelText) => {
            const labels = Array.from(document.querySelectorAll('label'));
            const label = labels.find((el) => (el.innerText || '').trim().includes(labelText));
            if (!label) return null;
            const input = label.querySelector('input[type="checkbox"]');
            if (!input) return null;
            if (!input.checked) input.click();
            return input.checked;
        }""",
        label_text,
    )
    if checked is None:
        raise RuntimeError(f"Could not find checkbox: {label_text}")


async def click_last_visible_ok(page: Page) -> None:
    ok_buttons = page.get_by_role("button", name="OK")
    for index in reversed(range(await ok_buttons.count())):
        button = ok_buttons.nth(index)
        try:
            if await button.is_visible(timeout=1000):
                await button.click()
                return
        except PlaywrightTimeoutError:
            continue
    await click_button_by_text_or_label(page, "OK")


async def login(page: Page, username: str, password: str) -> None:
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await fill_first_visible(
        page,
        ["input[name='username']", "input[type='email']", "input[type='text']", "#username"],
        username,
    )
    await fill_first_visible(
        page,
        ["input[name='password']", "input[type='password']", "#password"],
        password,
    )
    submit = page.locator("button[type='submit'], input[type='submit'], #submitBtn").first
    if await submit.count():
        await submit.click()
    else:
        await page.keyboard.press("Enter")
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(5000)
    await click_if_visible(page, "text=NO, THANKS")
    await click_if_visible(page, "text=ACCEPT COOKIES")
    for label in ("NO, THANKS", "ACCEPT COOKIES"):
        try:
            button = page.get_by_text(label, exact=False).first
            if await button.is_visible(timeout=1000):
                await button.click()
                await page.wait_for_timeout(800)
        except PlaywrightTimeoutError:
            pass
    text = await snapshot(page, "01-after-login")
    if "paxus.paxstore.us/admin" not in page.url and "Terminal Management" not in text:
        raise RuntimeError("Login did not reach the PAX admin page")


async def open_terminal_management(page: Page) -> None:
    await page.locator("#left_menu_terminal_management").click()
    await page.wait_for_timeout(6000)
    await snapshot(page, "02-terminal-management")


async def add_merchant(page: Page, data: PaxProvisioningData, submit: bool) -> None:
    if data.merchant_display_name in await page.locator("body").inner_text():
        await page.get_by_text(data.merchant_display_name, exact=True).first.click()
        await page.wait_for_timeout(2500)
        return

    await click_button_by_text_or_label(page, "Add Reseller/Merchant")
    await page.wait_for_timeout(1200)
    await page.get_by_text("Add Merchant", exact=True).click()
    await page.wait_for_timeout(1500)
    await page.locator("#name").fill(data.merchant_display_name)
    await ensure_checkbox_by_label(page, "Activate merchant")
    await snapshot(page, "03-before-add-merchant")

    if not submit:
        return

    await click_last_visible_ok(page)
    await page.wait_for_timeout(4000)
    text = await snapshot(page, "04-after-add-merchant")
    if data.merchant_display_name not in text:
        raise RuntimeError("Merchant was not visible after creation attempt")


async def select_merchant(page: Page, merchant_display_name: str) -> None:
    locator = page.get_by_text(merchant_display_name, exact=True).first
    try:
        if await locator.is_visible(timeout=2500):
            await locator.click()
        else:
            raise PlaywrightTimeoutError("merchant text is not visible")
    except PlaywrightTimeoutError:
        clicked = await page.evaluate(
            """(name) => {
                const nodes = Array.from(document.querySelectorAll('*'));
                const node = nodes.find((el) => (el.innerText || '').trim() === name);
                if (!node) return false;
                node.scrollIntoView({block: 'center', inline: 'center'});
                node.click();
                return true;
            }""",
            merchant_display_name,
        )
        if not clicked:
            raise RuntimeError(f"Could not select merchant: {merchant_display_name}")
    await page.wait_for_timeout(3000)
    await snapshot(page, "05-selected-merchant")


async def add_terminal(page: Page, data: PaxProvisioningData, device: TerminalDevice, submit: bool) -> None:
    await select_merchant(page, data.merchant_display_name)
    if device.serial_number in await page.locator("body").inner_text():
        print(f"{device.role}-terminal-create-result=already-visible")
        return
    await click_button_by_text_or_label(page, "TERMINAL")
    await page.wait_for_timeout(1500)

    await page.locator("#name").fill(device.display_name(data))
    await page.get_by_text("Immediately", exact=True).click()
    await page.locator("#serialNo").fill(device.serial_number)
    await page.wait_for_timeout(3500)
    before_text = await snapshot(page, f"06-before-add-{device.role}-terminal")

    if "PAX" not in before_text or (device.expected_model and device.expected_model not in before_text):
        expected = f"PAX {device.expected_model}" if device.expected_model else "PAX"
        print(f"warning: expected manufacturer/model {expected} was not visible before submit")

    if not submit:
        return

    await click_last_visible_ok(page)
    await page.wait_for_timeout(5000)
    after_text = await snapshot(page, f"07-after-add-{device.role}-terminal")
    duplicate_markers = [
        "has been registered",
        "already",
        "registered",
        "exist",
        "duplicate",
    ]
    if any(marker.lower() in after_text.lower() for marker in duplicate_markers):
        print(f"{device.role}-terminal-create-result=duplicate-or-existing")
        return
    if device.display_name(data) not in after_text and device.serial_number not in after_text:
        raise RuntimeError("Terminal creation result was unclear; inspect 07-after-add-terminal screenshot/text")


async def select_terminal(page: Page, data: PaxProvisioningData, device: TerminalDevice) -> None:
    terminal_name = device.display_name(data)
    body_text = await page.locator("body").inner_text(timeout=8000)
    if "Terminal Details" in body_text and device.serial_number in body_text and terminal_name in body_text:
        await snapshot(page, f"selected-{device.role}-terminal")
        return

    try:
        if await page.locator("#left_menu_terminal_management").is_visible(timeout=2500):
            await page.locator("#left_menu_terminal_management").click()
            await page.wait_for_timeout(5000)
    except PlaywrightTimeoutError:
        pass

    for locator in (
        page.get_by_text(terminal_name, exact=True).first,
        page.get_by_text(device.serial_number, exact=False).first,
    ):
        try:
            if await locator.is_visible(timeout=2500):
                await locator.click()
                await page.wait_for_timeout(2500)
                await snapshot(page, f"selected-{device.role}-terminal")
                return
        except PlaywrightTimeoutError:
            continue

    await select_merchant(page, data.merchant_display_name)
    for locator in (
        page.get_by_text(terminal_name, exact=True).first,
        page.get_by_text(device.serial_number, exact=False).first,
    ):
        try:
            if await locator.is_visible(timeout=2500):
                await locator.click()
                await page.wait_for_timeout(2500)
                await snapshot(page, f"selected-{device.role}-terminal")
                return
        except PlaywrightTimeoutError:
            continue
    raise RuntimeError(f"Could not select {device.role} terminal: {terminal_name}")


async def open_push_task(page: Page) -> None:
    await click_button_or_text(page, "App & Firmware")
    await page.wait_for_timeout(1500)
    await click_button_or_text(page, "Push Task")
    await page.wait_for_timeout(2000)
    await snapshot(page, "08-push-task")


async def push_latest_firmware(page: Page, submit: bool) -> None:
    await click_button_or_text(page, "Push Firmware")
    await page.wait_for_timeout(1500)
    current_text = await page.locator("body").inner_text(timeout=8000)
    if "Uniphiz_" in current_text and ("Active" in current_text or "Activated" in current_text or "Completed" in current_text):
        await snapshot(page, "09-existing-firmware-task")
        return
    if "Uniphiz_" in current_text and "ACTIVATE" in current_text:
        await snapshot(page, "09-existing-firmware-task")
        if submit:
            await activate_current_task(page, "10-after-firmware-push")
        return

    await click_button_by_text_or_label(page, "Add Firmware")
    await page.wait_for_timeout(2500)
    await snapshot(page, "09-firmware-list")

    await select_first_result_row(page)
    if not submit:
        return

    await click_last_visible_ok(page)
    await page.wait_for_timeout(2500)
    after_ok_text = await snapshot(page, "09-after-firmware-ok")
    if "Active terminal firmware already exists" in after_ok_text:
        return
    await activate_current_task(page, "10-after-firmware-push")


async def activate_current_task(page: Page, snapshot_name: str) -> None:
    await click_button_or_text(page, "ACTIVATE")
    await page.wait_for_timeout(1000)
    await click_last_visible_ok(page)
    await page.wait_for_timeout(3000)
    await snapshot(page, snapshot_name)


async def push_named_app(
    page: Page,
    *,
    query: str,
    app_name: str,
    submit: bool,
    activate: bool,
    snapshot_prefix: str,
) -> None:
    await click_button_or_text(page, "Push App")
    await page.wait_for_timeout(1500)
    await click_button_by_text_or_label(page, "Add App")
    await page.wait_for_timeout(1500)

    search = page.locator("input#Search:visible, div.dialog_section_head input:visible, input[placeholder='Search']:visible").first
    await search.fill(query)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(2500)
    await snapshot(page, f"{snapshot_prefix}-app-search")
    await click_button_by_text_or_label(page, app_name)
    await page.wait_for_timeout(1000)

    close_button = page.get_by_role("button", name="CLOSE")
    try:
        if await close_button.last.is_visible(timeout=1500):
            await close_button.last.click()
            await page.wait_for_timeout(1000)
    except PlaywrightTimeoutError:
        pass

    await select_first_result_row(page)
    await snapshot(page, f"{snapshot_prefix}-before-app-ok")
    if not submit:
        return

    await click_last_visible_ok(page)
    await page.wait_for_timeout(2500)
    await snapshot(page, f"{snapshot_prefix}-after-app-ok")

    if activate:
        await activate_current_task(page, f"{snapshot_prefix}-after-app-activate")


async def push_tsys_app(page: Page, data: PaxProvisioningData, submit: bool, activate_payment_app: bool) -> None:
    await push_named_app(
        page,
        query="tsys",
        app_name="BroadPOS TSYS Sierra",
        submit=submit,
        activate=False,
        snapshot_prefix="11-tsys",
    )
    if not submit:
        return

    await page.get_by_role("button", name="Push Template").click()
    await page.wait_for_timeout(1000)
    await page.get_by_text("Parameter File:retail.zip").click()
    await page.wait_for_timeout(1000)
    await page.get_by_role("button", name="USE THE CURRENT TEMPLATE").click()
    await page.wait_for_timeout(2500)
    await page.get_by_role("button", name="TSYS").click()
    await page.wait_for_timeout(1500)

    await fill_tsys_parameters(page, data)
    await snapshot(page, "12-before-tsys-next")

    if submit:
        await page.get_by_role("button", name="NEXT").click()
        await page.wait_for_timeout(3000)
        await snapshot(page, "13-after-tsys-next")
        if activate_payment_app:
            await activate_current_task(page, "14-after-tsys-activate")


async def fill_by_id(page: Page, field_id: str, value: str) -> None:
    if not value:
        return
    locator = page.locator(f'[id="{field_id}"]')
    await locator.fill(value)


async def select_autocomplete_option(input_locator: Locator, query: str, option_text: str) -> None:
    await input_locator.fill(query)
    await input_locator.page.get_by_text(option_text, exact=True).click()


async def fill_tsys_parameters(page: Page, data: PaxProvisioningData) -> None:
    await fill_by_id(page, "6_tsys_F1_tsys_param_merchantName", data.dba_name)
    await fill_by_id(page, "0_tsys_F1_tsys_param_BIN", data.bin)
    await fill_by_id(page, "1_tsys_F1_tsys_param_agentNumber", data.agent_bank)
    await fill_by_id(page, "2_tsys_F1_tsys_param_chainNumber", data.chain)
    await fill_by_id(page, "3_tsys_F1_tsys_param_MID", data.merchant_number)
    await fill_by_id(page, "4_tsys_F1_tsys_param_storeNumber", data.store_number)
    await fill_by_id(page, "5_tsys_F1_tsys_param_terminalNumber", data.terminal_number)
    await fill_by_id(page, "7_tsys_F1_tsys_param_merchantCity", data.city)
    await fill_by_id(page, "9_tsys_F1_tsys_param_cityCode", data.zip)
    await fill_by_id(page, "13_tsys_F1_tsys_param_categoryCode", data.mcc)
    await fill_by_id(page, "19_tsys_F1_tsys_param_TID", data.terminal_id_number)

    if data.state:
        state_input = page.locator('[id="8_tsys_F1_tsys_param_merchantState"]')
        await select_autocomplete_option(state_input, data.state[:2], data.state)
    timezone_input = page.locator('[id="17_tsys_F1_tsys_param_timeZone"]')
    await select_autocomplete_option(timezone_input, data.timezone_query, data.timezone_option)


def parse_steps(raw_steps: str) -> set[str]:
    if raw_steps in {"all", "single-all"}:
        return {"merchant", "terminal", "firmware", "tsys"}
    if raw_steps == "two-device":
        return {"merchant", "terminals", "pos-apps", "pinpad-apps"}
    return {step.strip() for step in raw_steps.split(",") if step.strip()}


def make_data_for_device(data: PaxProvisioningData, device: TerminalDevice) -> PaxProvisioningData:
    return PaxProvisioningData(
        dba_name=data.dba_name,
        merchant_number=data.merchant_number,
        serial_number=device.serial_number,
        merchant_display_name=data.merchant_display_name,
        terminal_display_name=device.display_name(data),
        bin=data.bin,
        agent_bank=data.agent_bank,
        chain=data.chain,
        store_number=data.store_number,
        terminal_number=data.terminal_number,
        city=data.city,
        state=data.state,
        zip=data.zip,
        mcc=data.mcc,
        terminal_id_number=data.terminal_id_number,
        timezone_query=data.timezone_query,
        timezone_option=data.timezone_option,
    )


async def download_var_from_kit_dashboard(
    merchant_number: str,
    *,
    settings: Settings,
    save_dir: Path,
    headed: bool,
    verification_code: str | None,
) -> Path | None:
    if not settings.kit_dashboard_email or not settings.kit_dashboard_password:
        return None
    if not KIT_DASHBOARD_AGENT_DIR.exists():
        return None

    sys.path.insert(0, str(KIT_DASHBOARD_AGENT_DIR / "src"))
    from merchant_data.models import KitCredentials
    from merchant_data.services.kit_merchant_lookup import MerchantLookupService

    credentials = KitCredentials(
        email=settings.kit_dashboard_email,
        password=settings.kit_dashboard_password,
        base_url=settings.kit_dashboard_url,
        storage_state=PROJECT_ROOT / settings.kit_dashboard_storage_state,
        verification_code=verification_code,
    )
    service = MerchantLookupService(
        credentials,
        headless=not headed,
        debug_dir=PROJECT_ROOT / "tmp" / "kit-dashboard-debug",
    )
    print(f"Resolving VAR from Kit Dashboard for Merchant Number {merchant_number}...", flush=True)
    result = await asyncio.wait_for(service.download_var_by_id(merchant_number, save_dir), timeout=120)
    return result.saved_path


def download_var_from_email(merchant_number: str, *, settings: Settings) -> Path | None:
    if (
        settings.mail_provider != "imap"
        or not settings.mail_imap_host
        or not settings.mail_username
        or not settings.mail_password
    ):
        return None

    inbox = ImapInboxClient(
        host=settings.mail_imap_host,
        port=settings.mail_imap_port,
        username=settings.mail_username,
        password=settings.mail_password,
        mailbox=settings.mail_imap_mailbox,
        scan_limit=settings.mail_scan_limit,
    )
    attachment = inbox.find_latest_var_pdf(merchant_number)
    return attachment.path if attachment else None


async def resolve_var_pdf(args: argparse.Namespace, settings: Settings) -> Path:
    if args.pdf:
        return args.pdf
    if not args.merchant_number:
        raise RuntimeError("--merchant-number is required when --pdf is not provided")

    sources = ["kit-dashboard", "email"] if args.var_source == "auto" else [args.var_source]
    last_errors: list[str] = []
    for source in sources:
        try:
            if source == "kit-dashboard":
                path = await download_var_from_kit_dashboard(
                    args.merchant_number,
                    settings=settings,
                    save_dir=args.var_download_dir,
                    headed=args.headed,
                    verification_code=args.kit_verification_code,
                )
            elif source == "email":
                path = download_var_from_email(args.merchant_number, settings=settings)
            else:
                path = None
            if path:
                print(f"VAR PDF resolved from {source}: {path}")
                return path
        except TimeoutError:
            last_errors.append(
                f"{source}: timed out while resolving VAR PDF. If KIT Dashboard requested 2FA, rerun with --kit-verification-code."
            )
        except Exception as exc:
            last_errors.append(f"{source}: {exc}")

    details = "; ".join(last_errors) if last_errors else "no configured source returned a PDF"
    raise RuntimeError(f"Could not resolve VAR PDF for Merchant Number {args.merchant_number}: {details}")


async def provision_single_terminal(
    page: Page,
    data: PaxProvisioningData,
    *,
    steps: set[str],
    submit: bool,
    activate_payment_app: bool,
) -> None:
    device = TerminalDevice(role="single", serial_number=data.serial_number)
    if "merchant" in steps:
        await add_merchant(page, data, submit)
    if "terminal" in steps:
        await add_terminal(page, data, device, submit)
    if "firmware" in steps or "tsys" in steps:
        await select_terminal(page, data, device)
        await open_push_task(page)
    if "firmware" in steps:
        await push_latest_firmware(page, submit)
    if "tsys" in steps:
        await select_terminal(page, data, device)
        await open_push_task(page)
        await push_tsys_app(page, data, submit, activate_payment_app)


async def provision_two_device_workflow(
    page: Page,
    data: PaxProvisioningData,
    *,
    pos_device: TerminalDevice,
    pinpad_device: TerminalDevice,
    steps: set[str],
    submit: bool,
    activate_payment_app: bool,
) -> None:
    if "merchant" in steps:
        await add_merchant(page, data, submit)
    if "terminals" in steps:
        await add_terminal(page, data, pos_device, submit)
        await add_terminal(page, data, pinpad_device, submit)

    if "pos-apps" in steps:
        await select_terminal(page, data, pos_device)
        await open_push_task(page)
        await push_latest_firmware(page, submit)
        await select_terminal(page, data, pos_device)
        await open_push_task(page)
        await push_named_app(
            page,
            query="kit stock",
            app_name="KIT Stock",
            submit=submit,
            activate=True,
            snapshot_prefix="pos-kit-stock",
        )
        await push_named_app(
            page,
            query="kit merchant",
            app_name="KIT Merchant",
            submit=submit,
            activate=True,
            snapshot_prefix="pos-kit-merchant",
        )

    if "pinpad-apps" in steps:
        pinpad_data = make_data_for_device(data, pinpad_device)
        await select_terminal(page, pinpad_data, pinpad_device)
        await open_push_task(page)
        await push_latest_firmware(page, submit)
        await select_terminal(page, pinpad_data, pinpad_device)
        await open_push_task(page)
        if pinpad_device.needs_back_screen():
            await push_named_app(
                page,
                query="kit back screen",
                app_name="KIT Back Screen",
                submit=submit,
                activate=True,
                snapshot_prefix="pinpad-kit-back-screen",
            )
        await push_tsys_app(page, pinpad_data, submit, activate_payment_app)


def build_plan_summary(
    data: PaxProvisioningData,
    *,
    pdf_path: Path,
    pos_device: TerminalDevice | None,
    pinpad_device: TerminalDevice | None,
    steps: set[str],
    activate_payment_app: bool,
) -> dict:
    summary = {
        "pdf_path": str(pdf_path),
        "merchant_display_name": data.merchant_display_name,
        "merchant_number": data.merchant_number,
        "dba_name": data.dba_name,
        "steps": sorted(steps),
        "var_numbers": {
            "bin": data.bin,
            "agent_bank": data.agent_bank,
            "chain": data.chain,
            "merchant_number": data.merchant_number,
            "store_number": data.store_number,
            "terminal_number": data.terminal_number,
            "city": data.city,
            "state": data.state,
            "city_code_zip": data.zip,
            "mcc": data.mcc,
            "terminal_id_number": data.terminal_id_number,
            "timezone": data.timezone_option,
        },
        "payment_app_activation": "activate" if activate_payment_app else "leave_pending_for_review",
    }
    devices = []
    if pos_device:
        devices.append(
            {
                "role": "pos",
                "serial_number": pos_device.serial_number,
                "expected_model": pos_device.expected_model,
                "terminal_name": pos_device.display_name(data),
                "firmware": "latest_before_apps",
                "apps": ["KIT POS (expected automatic)", "KIT Stock", "KIT Merchant"],
                "activate_apps": True,
            }
        )
    if pinpad_device:
        pinpad_apps = ["BroadPOS TSYS Sierra"]
        if pinpad_device.needs_back_screen():
            pinpad_apps.insert(0, "KIT Back Screen")
        devices.append(
            {
                "role": "pinpad",
                "serial_number": pinpad_device.serial_number,
                "expected_model": pinpad_device.expected_model,
                "terminal_name": pinpad_device.display_name(data),
                "firmware": "latest_before_apps",
                "apps": pinpad_apps,
                "tsys_template": "Parameter File:retail.zip",
                "activate_payment_app": activate_payment_app,
            }
        )
    if not devices:
        devices.append(
            {
                "role": "single",
                "serial_number": data.serial_number,
                "terminal_name": data.terminal_display_name,
            }
        )
    summary["devices"] = devices
    return summary


def build_run_history_record(
    args: argparse.Namespace,
    *,
    status: str,
    pdf_path: Path | None = None,
    data: PaxProvisioningData | None = None,
    error: Exception | None = None,
) -> dict:
    record = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "mode": "headed" if args.headed else "headless",
        "plan_only": args.plan_only,
        "submit": args.submit,
        "steps": sorted(parse_steps(args.steps)),
        "var_source": args.var_source,
        "pdf_path": str(pdf_path) if pdf_path else None,
        "merchant_number_arg": args.merchant_number,
        "merchant_number_override": args.merchant_number_override,
        "pos_serial": args.pos_serial,
        "pinpad_serial": args.pinpad_serial,
        "serial_number": args.serial_number,
        "pos_model": args.pos_model,
        "pinpad_model": args.pinpad_model,
        "pinpad_back_screen": args.pinpad_back_screen,
        "activate_payment_app": args.activate_payment_app,
        "screenshots_dir": str(SCREENSHOT_DIR),
    }
    if data:
        record.update(
            {
                "dba_name": data.dba_name,
                "merchant_number": data.merchant_number,
                "merchant_display_name": data.merchant_display_name,
                "terminal_id_number": data.terminal_id_number,
                "timezone": data.timezone_option,
            }
        )
    if error:
        record["error_type"] = type(error).__name__
        record["error"] = str(error)
    return record


def append_run_history(record: dict) -> None:
    RUN_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with RUN_HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


async def main() -> None:
    load_dotenv()
    load_dotenv(KIT_DASHBOARD_AGENT_DIR / ".env")
    parser = argparse.ArgumentParser(description="Provision PAX merchant, terminal, and app push tasks from a VAR PDF.")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--merchant-number", help="Merchant Number used to find/download the VAR PDF when --pdf is omitted.")
    parser.add_argument("--serial-number", help="Legacy single-device serial number.")
    parser.add_argument("--pos-serial", help="POS serial number for the two-device workflow.")
    parser.add_argument("--pinpad-serial", help="PIN pad serial number for the two-device workflow.")
    parser.add_argument("--pos-model", default="L1400")
    parser.add_argument("--pinpad-model", default="A3700")
    back_screen_group = parser.add_mutually_exclusive_group()
    back_screen_group.add_argument(
        "--pinpad-back-screen",
        dest="pinpad_back_screen",
        action="store_true",
        help="Force installing KIT Back Screen on the PIN pad.",
    )
    back_screen_group.add_argument(
        "--no-pinpad-back-screen",
        dest="pinpad_back_screen",
        action="store_false",
        help="Do not install KIT Back Screen on the PIN pad.",
    )
    parser.set_defaults(pinpad_back_screen=None)
    parser.add_argument("--var-source", choices=["auto", "kit-dashboard", "email"], default="auto")
    parser.add_argument("--var-download-dir", type=Path, default=DEFAULT_VAR_DOWNLOAD_DIR)
    parser.add_argument("--kit-verification-code", help="KIT Dashboard 2FA code when the session requires verification.")
    parser.add_argument(
        "--merchant-number-override",
        help="Optional override for the VAR Merchant Number. Normally this is read from the PDF.",
    )
    parser.add_argument(
        "--steps",
        default="merchant,terminal",
        help="Comma list. Single-device: merchant,terminal,firmware,tsys/all. Two-device: merchant,terminals,pos-apps,pinpad-apps/two-device.",
    )
    parser.add_argument("--submit", action="store_true", help="Create PAX tasks. Without this, stops before final OK/NEXT buttons.")
    parser.add_argument(
        "--activate-payment-app",
        action="store_true",
        help="Activate BroadPOS TSYS Sierra after filling TSYS parameters. Default keeps it pending for review.",
    )
    parser.add_argument("--plan-only", action="store_true", help="Resolve/read VAR and print the workflow plan without opening PAX Store.")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    pdf_path = await resolve_var_pdf(args, settings)
    primary_serial = args.pinpad_serial or args.serial_number or args.pos_serial
    if not primary_serial:
        raise RuntimeError("Provide --serial-number for single-device mode or --pos-serial/--pinpad-serial for two-device mode")

    data = PaxProvisioningData.from_pdf(pdf_path, primary_serial, args.merchant_number_override or args.merchant_number)
    steps = parse_steps(args.steps)
    pos_device = TerminalDevice("pos", args.pos_serial, args.pos_model) if args.pos_serial else None
    pinpad_device = (
        TerminalDevice("pinpad", args.pinpad_serial, args.pinpad_model, args.pinpad_back_screen)
        if args.pinpad_serial
        else None
    )
    if args.plan_only:
        plan_summary = build_plan_summary(
            data,
            pdf_path=pdf_path,
            pos_device=pos_device,
            pinpad_device=pinpad_device,
            steps=steps,
            activate_payment_app=args.activate_payment_app,
        )
        append_run_history(build_run_history_record(args, status="success", pdf_path=pdf_path, data=data))
        print(json.dumps(plan_summary, indent=2, ensure_ascii=True))
        return

    username = input("PAX username: ").strip()
    password = getpass("PAX password: ")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not args.headed)
            context = await browser.new_context(viewport={"width": 1440, "height": 1000})
            page = await context.new_page()
            page.set_default_timeout(20000)

            await login(page, username, password)
            await open_terminal_management(page)
            if args.pos_serial and args.pinpad_serial:
                await provision_two_device_workflow(
                    page,
                    data,
                    pos_device=pos_device,
                    pinpad_device=pinpad_device,
                    steps=steps,
                    submit=args.submit,
                    activate_payment_app=args.activate_payment_app,
                )
            else:
                await provision_single_terminal(
                    page,
                    data,
                    steps=steps,
                    submit=args.submit,
                    activate_payment_app=args.activate_payment_app,
                )

            await context.close()
            await browser.close()
        append_run_history(build_run_history_record(args, status="success", pdf_path=pdf_path, data=data))
    except Exception as exc:
        append_run_history(build_run_history_record(args, status="failure", pdf_path=pdf_path, data=data, error=exc))
        raise


if __name__ == "__main__":
    asyncio.run(main())
