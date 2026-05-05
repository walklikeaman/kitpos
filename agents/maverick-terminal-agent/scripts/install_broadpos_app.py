"""
Install BroadPOS TSYS Sierra app and fill TSYS parameters.
Continues from existing PAX portal session.

⚠️ LEGACY FLOW — DO NOT USE FOR NEW PROVISIONING.

The `push_app()` function below searches the app catalog for "tsys" and
manually selects "BroadPOS TSYS Sierra" + Parameter File "retail.zip". This is
NO LONGER the canonical procedure.

The current rule (see `docs/PAXSTORE_PROVISIONING_RULES.md`, §4) is:
    Push Task → Push App dialog → "Push Template" tab → tick template → OK
The template auto-installs BroadPOS TSYS Sierra with the right Parameter File.

This module is kept only for the TSYS field mapping in `fill_tsys_parameters()`
which IS still correct. Reuse that helper from new code; ignore `push_app()`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright


LOGIN_URL = "https://auth.paxstore.us/passport/login?client_id=admin&market=paxus"
PORTAL_URL = "https://paxus.paxstore.us/admin/#/welcome"
SCREENSHOT_DIR = Path("tmp/screenshots_app_install")


@dataclass(slots=True)
class TsysParams:
    """TSYS parameters from VAR"""
    merchant_name: str  # DBA
    bin: str
    agent_bank: str
    chain: str
    merchant_number: str  # MID
    store_number: str
    terminal_number: str
    city: str
    state: str
    zip: str
    mcc: str
    tid: str  # V Number extracted


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


async def select_autocomplete_option(input_locator, query: str, option_text: str) -> None:
    await input_locator.fill(query)
    await input_locator.page.get_by_text(option_text, exact=True).click()


async def fill_by_id(page: Page, field_id: str, value: str) -> None:
    if not value:
        return
    locator = page.locator(f'[id="{field_id}"]')
    await locator.fill(value)


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


async def navigate_to_terminal(page: Page, merchant_display_name: str, terminal_display_name: str) -> None:
    """Navigate to terminal in Terminal Management"""
    await page.locator("#left_menu_terminal_management").click()
    await page.wait_for_timeout(6000)

    # Click on merchant
    await page.get_by_text(merchant_display_name, exact=True).first.click()
    await page.wait_for_timeout(3000)

    # Click on terminal
    await page.get_by_text(terminal_display_name, exact=True).first.click()
    await page.wait_for_timeout(3000)
    await snapshot(page, "02-terminal-selected")


async def push_app(page: Page, params: TsysParams) -> None:
    """Push App workflow: search TSYS, select BroadPOS, fill TSYS params"""
    # Click App & Firmware tab
    await page.get_by_text("App & Firmware", exact=True).click()
    await page.wait_for_timeout(2000)

    # Click Push Task tab
    await page.get_by_text("Push Task", exact=True).click()
    await page.wait_for_timeout(2000)
    await snapshot(page, "03-push-task")

    # Click Push App button
    await page.get_by_role("button", name="Push App").click()
    await page.wait_for_timeout(1500)

    # Click Add App
    await click_button_by_text_or_label(page, "Add App")
    await page.wait_for_timeout(1500)

    # Search for TSYS
    search = page.locator("#Search, div.dialog_section_head input").first
    await search.fill("tsys")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(2500)
    await snapshot(page, "04-app-search-tsys")

    # Select BroadPOS TSYS Sierra
    await click_button_by_text_or_label(page, "BroadPOS TSYS Sierra")
    await page.wait_for_timeout(1000)

    # Close dialog if visible
    close_button = page.get_by_role("button", name="CLOSE")
    try:
        if await close_button.last.is_visible(timeout=1500):
            await close_button.last.click()
            await page.wait_for_timeout(1000)
    except PlaywrightTimeoutError:
        pass

    # Select first checkbox
    first_checkbox = page.locator("tbody tr").first.locator("input[type='checkbox']").first
    await first_checkbox.click()
    await click_last_visible_ok(page)
    await page.wait_for_timeout(2500)

    # Push Template
    await page.get_by_role("button", name="Push Template").click()
    await page.wait_for_timeout(1000)

    # Select retail.zip
    await page.get_by_text("Parameter File:retail.zip").click()
    await page.wait_for_timeout(1000)

    # Use current template
    await page.get_by_role("button", name="USE THE CURRENT TEMPLATE").click()
    await page.wait_for_timeout(2500)

    # Click TSYS section
    await page.get_by_role("button", name="TSYS").click()
    await page.wait_for_timeout(1500)

    # Fill TSYS parameters
    await fill_tsys_parameters(page, params)
    await snapshot(page, "05-before-tsys-next")

    # Click NEXT
    await page.get_by_role("button", name="NEXT").click()
    await page.wait_for_timeout(3000)
    await snapshot(page, "06-after-tsys-next")


async def fill_tsys_parameters(page: Page, params: TsysParams) -> None:
    """Fill all TSYS parameter fields"""
    await fill_by_id(page, "6_tsys_F1_tsys_param_merchantName", params.merchant_name)
    await fill_by_id(page, "0_tsys_F1_tsys_param_BIN", params.bin)
    await fill_by_id(page, "1_tsys_F1_tsys_param_agentNumber", params.agent_bank)
    await fill_by_id(page, "2_tsys_F1_tsys_param_chainNumber", params.chain)
    await fill_by_id(page, "3_tsys_F1_tsys_param_MID", params.merchant_number)
    await fill_by_id(page, "4_tsys_F1_tsys_param_storeNumber", params.store_number)
    await fill_by_id(page, "5_tsys_F1_tsys_param_terminalNumber", params.terminal_number)
    await fill_by_id(page, "7_tsys_F1_tsys_param_merchantCity", params.city)
    await fill_by_id(page, "9_tsys_F1_tsys_param_cityCode", params.zip)
    await fill_by_id(page, "13_tsys_F1_tsys_param_categoryCode", params.mcc)
    await fill_by_id(page, "19_tsys_F1_tsys_param_TID", params.tid)

    # State: autocomplete
    if params.state:
        state_input = page.locator('[id="8_tsys_F1_tsys_param_merchantState"]')
        await select_autocomplete_option(state_input, params.state[:2], params.state)

    # Timezone: autocomplete PST
    timezone_input = page.locator('[id="17_tsys_F1_tsys_param_timeZone"]')
    await select_autocomplete_option(timezone_input, "pst", "708-PST")


async def main() -> None:
    # TSYS parameters from API
    params = TsysParams(
        merchant_name="Pady C Store",
        bin="422108",
        agent_bank="081960",
        chain="081960",
        merchant_number="201100305938",
        store_number="0002",
        terminal_number="7001",
        city="Midwest City",
        state="Oklahoma",  # Corrected from API (which says Oregon)
        zip="73110",
        mcc="5411",
        tid="V6612507",  # V Number extracted from API
    )

    username = input("PAX username: ").strip()
    password = getpass("PAX password: ")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # headless by default; pass headless=False for debugging
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await context.new_page()
        page.set_default_timeout(20000)

        await login(page, username, password)

        # Navigate to Pady C Store terminal
        merchant_display_name = "Pady C Store 201100305938"
        terminal_display_name = "Pady C Store 2290664794"
        await navigate_to_terminal(page, merchant_display_name, terminal_display_name)

        # Push BroadPOS TSYS Sierra app
        await push_app(page, params)

        print("\n✅ BroadPOS TSYS Sierra app installed and TSYS parameters filled!")
        print(f"Screenshots: {SCREENSHOT_DIR}")

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
