from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

from playwright.async_api import Locator
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from maverick_agent.parsers.var_pdf import VarPdfParser


LOGIN_URL = "https://auth.paxstore.us/passport/login?client_id=admin&market=paxus"
SCREENSHOT_DIR = Path("tmp/screenshots")


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
    raise RuntimeError("Could not find visible OK button")


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
    text = await snapshot(page, "01-after-login")
    if "Terminal Management" not in text:
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
    await page.get_by_text(merchant_display_name, exact=True).first.click()
    await page.wait_for_timeout(3000)
    await snapshot(page, "05-selected-merchant")


async def add_terminal(page: Page, data: PaxProvisioningData, submit: bool) -> None:
    await select_merchant(page, data.merchant_display_name)
    await click_button_by_text_or_label(page, "TERMINAL")
    await page.wait_for_timeout(1500)

    await page.locator("#name").fill(data.terminal_display_name)
    await page.get_by_text("Immediately", exact=True).click()
    await page.locator("#serialNo").fill(data.serial_number)
    await page.wait_for_timeout(3500)
    before_text = await snapshot(page, "06-before-add-terminal")

    if "PAX" not in before_text or "A35" not in before_text:
        print("warning: expected manufacturer/model PAX A35 was not visible before submit")

    if not submit:
        return

    await click_last_visible_ok(page)
    await page.wait_for_timeout(5000)
    after_text = await snapshot(page, "07-after-add-terminal")
    duplicate_markers = [
        "has been registered",
        "already",
        "registered",
        "exist",
        "duplicate",
    ]
    if any(marker.lower() in after_text.lower() for marker in duplicate_markers):
        print("terminal-create-result=duplicate-or-existing")
        return
    if data.terminal_display_name not in after_text and data.serial_number not in after_text:
        raise RuntimeError("Terminal creation result was unclear; inspect 07-after-add-terminal screenshot/text")


async def open_push_task(page: Page) -> None:
    await page.get_by_role("button", name="App & Firmware").click()
    await page.wait_for_timeout(1500)
    await page.get_by_role("button", name="Push Task").click()
    await page.wait_for_timeout(2000)
    await snapshot(page, "08-push-task")


async def push_latest_firmware(page: Page, submit: bool) -> None:
    await page.get_by_role("button", name="Push Firmware").click()
    await page.wait_for_timeout(1500)
    await click_button_by_text_or_label(page, "Add Firmware")
    await page.wait_for_timeout(2500)
    await snapshot(page, "09-firmware-list")

    first_checkbox = page.locator("tbody tr").first.locator("input[type='checkbox']").first
    await first_checkbox.click()
    if not submit:
        return

    await click_last_visible_ok(page)
    await page.wait_for_timeout(2500)
    await page.get_by_role("button", name="ACTIVATE").click()
    await page.wait_for_timeout(1000)
    await click_last_visible_ok(page)
    await page.wait_for_timeout(3000)
    await snapshot(page, "10-after-firmware-push")


async def push_tsys_app(page: Page, data: PaxProvisioningData, submit: bool) -> None:
    await page.get_by_role("button", name="Push App").click()
    await page.wait_for_timeout(1500)
    await click_button_by_text_or_label(page, "Add App")
    await page.wait_for_timeout(1500)

    search = page.locator("#Search, div.dialog_section_head input").first
    await search.fill("tsys")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(2500)
    await snapshot(page, "11-app-search-tsys")
    await click_button_by_text_or_label(page, "BroadPOS TSYS Sierra")
    await page.wait_for_timeout(1000)

    close_button = page.get_by_role("button", name="CLOSE")
    try:
        if await close_button.last.is_visible(timeout=1500):
            await close_button.last.click()
            await page.wait_for_timeout(1000)
    except PlaywrightTimeoutError:
        pass

    first_checkbox = page.locator("tbody tr").first.locator("input[type='checkbox']").first
    await first_checkbox.click()
    await click_last_visible_ok(page)
    await page.wait_for_timeout(2500)

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
    if raw_steps == "all":
        return {"merchant", "terminal", "firmware", "tsys"}
    return {step.strip() for step in raw_steps.split(",") if step.strip()}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Provision PAX merchant, terminal, and TSYS push task from a VAR PDF.")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--serial-number", required=True)
    parser.add_argument(
        "--merchant-number-override",
        help="Optional override for the VAR Merchant Number. Normally this is read from the PDF.",
    )
    parser.add_argument("--steps", default="merchant,terminal", help="Comma list: merchant,terminal,firmware,tsys or all.")
    parser.add_argument("--submit", action="store_true", help="Actually click final OK/NEXT buttons. Without this, stops before submits.")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    data = PaxProvisioningData.from_pdf(args.pdf, args.serial_number, args.merchant_number_override)
    steps = parse_steps(args.steps)
    username = input("PAX username: ").strip()
    password = getpass("PAX password: ")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await context.new_page()
        page.set_default_timeout(20000)

        await login(page, username, password)
        await open_terminal_management(page)
        if "merchant" in steps:
            await add_merchant(page, data, args.submit)
        if "terminal" in steps:
            await add_terminal(page, data, args.submit)
        if "firmware" in steps or "tsys" in steps:
            await open_push_task(page)
        if "firmware" in steps:
            await push_latest_firmware(page, args.submit)
        if "tsys" in steps:
            await push_tsys_app(page, data, args.submit)

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
