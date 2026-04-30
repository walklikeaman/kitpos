from __future__ import annotations

import argparse
import asyncio
from getpass import getpass
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


DEFAULT_LOGIN_URL = "https://auth.paxstore.us/passport/login?client_id=admin&market=paxus"
STATE_PATH = Path("tmp/paxstore-state.json")
SCREENSHOT_DIR = Path("tmp/screenshots")


async def snapshot(page, name: str) -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=SCREENSHOT_DIR / f"{name}.png", full_page=True)
    text = await page.locator("body").inner_text(timeout=8000)
    (SCREENSHOT_DIR / f"{name}.txt").write_text(text[:12000], encoding="utf-8")
    print(f"\n--- {name} ---")
    print(f"URL: {page.url}")
    print(f"TITLE: {await page.title()}")
    print(text[:4000])
    return text


async def fill_first_visible(page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.is_visible(timeout=1500):
                await locator.fill(value)
                return True
        except PlaywrightTimeoutError:
            continue
    return False


async def click_if_visible(page, selector: str) -> bool:
    locator = page.locator(selector).first
    try:
        if await locator.is_visible(timeout=1200):
            await locator.click()
            return True
    except PlaywrightTimeoutError:
        return False
    return False


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe PAX Store login and admin landing page.")
    parser.add_argument("--login-url", default=DEFAULT_LOGIN_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--keep-state", action="store_true")
    args = parser.parse_args()

    username = input("PAX username: ").strip()
    password = getpass("PAX password: ")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await context.new_page()
        page.set_default_timeout(20000)

        await page.goto(args.login_url, wait_until="domcontentloaded")
        await snapshot(page, "01-login-page")

        filled_user = await fill_first_visible(
            page,
            [
                "input[name='username']",
                "input[name='email']",
                "input[type='email']",
                "input[type='text']",
                "input[placeholder*='User' i]",
                "input[placeholder*='Email' i]",
            ],
            username,
        )
        filled_password = await fill_first_visible(
            page,
            [
                "input[name='password']",
                "input[type='password']",
                "input[placeholder*='Password' i]",
            ],
            password,
        )
        if not filled_user or not filled_password:
            raise RuntimeError("Could not fill login fields.")

        submit = page.locator("button[type='submit'], input[type='submit']").first
        if await submit.count():
            await submit.click()
        else:
            await page.keyboard.press("Enter")

        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(5000)
        await click_if_visible(page, "text=NO, THANKS")
        await click_if_visible(page, "text=ACCEPT COOKIES")
        text = await snapshot(page, "02-after-login")

        success = "Terminal Management" in text and "/admin/#/welcome" in page.url
        await context.storage_state(path=STATE_PATH)
        await browser.close()

    if not args.keep_state and STATE_PATH.exists():
        STATE_PATH.unlink()

    if not success:
        raise RuntimeError("Login did not reach the expected PAX admin welcome page.")

    print("login-ok")


if __name__ == "__main__":
    asyncio.run(main())
