"""Browser session, login, navigation primitives for the 2026 PAX Store UI.

Handles: launching Chromium with a Supabase-saved session, logging in fresh
when needed, dismissing cookie banners, navigating to a specific terminal.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Page,
    async_playwright,
)

from maverick_agent.services.session_store import (
    delete_session,
    load_session,
    save_session,
)

LOGIN_URL = "https://auth.paxstore.us/passport/login?client_id=admin&market=paxus"
ADMIN_URL = "https://paxus.paxstore.us/admin/"
SESSION_KEY = "paxstore"


# ──────────────────────────────────────────────────────────────────────────────
# Screenshots
# ──────────────────────────────────────────────────────────────────────────────

async def shot(page: Page, name: str, debug_dir: Path | None = None) -> None:
    """Save a full-page screenshot. Silently swallows failures."""
    target_dir = debug_dir or Path("tmp/ui-debug")
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        await page.screenshot(path=str(target_dir / f"{name}.png"), full_page=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  [shot {name} failed: {exc}]")


# ──────────────────────────────────────────────────────────────────────────────
# Cookies
# ──────────────────────────────────────────────────────────────────────────────

async def dismiss_cookies(page: Page) -> bool:
    """Click any visible 'NO, THANKS' / Reject button on the cookies banner.

    Returns True if a banner was dismissed, False otherwise.
    """
    for label in ["NO, THANKS", "No, thanks", "Reject"]:
        try:
            btn = page.locator(f"button:has-text('{label}')").first
            if await btn.count() > 0:
                await btn.click(timeout=3000)
                await page.wait_for_timeout(400)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Login + session
# ──────────────────────────────────────────────────────────────────────────────

async def login_if_needed(page: Page, user: str, pw: str) -> bool:
    """Navigate to admin and ensure logged-in. Returns True if a fresh login was performed.

    Important: PAX redirects to auth.paxstore.us asynchronously after admin loads,
    so URL alone is unreliable. Wait for either the menu or the login form to
    appear, then inspect URL.
    """
    await page.goto(ADMIN_URL, wait_until="domcontentloaded", timeout=20000)
    with contextlib.suppress(Exception):
        await page.wait_for_selector(
            "#left_menu_terminal_management, input[name='username'], input[type='password']",
            timeout=15000,
        )
    await page.wait_for_timeout(1500)
    if "passport" in page.url.lower() or "auth.paxstore" in page.url.lower():
        print("→ logging in (session expired or missing)")
        await page.locator("input[name='username'], input[type='text']").first.fill(user, timeout=10000)
        await page.locator("input[name='password'], input[type='password']").first.fill(pw, timeout=10000)
        for sel in ["button[type='submit']", "button:has-text('Login')", "button:has-text('Sign in')"]:
            try:
                await page.locator(sel).first.click(timeout=4000)
                break
            except Exception:  # noqa: BLE001
                continue
        await page.wait_for_url("**/admin/**", timeout=30000)
        await page.wait_for_selector("#left_menu_terminal_management", timeout=20000)
        return True
    print("→ session still valid")
    return False


@contextlib.asynccontextmanager
async def launch_session(*, headless: bool = True, viewport: dict | None = None):
    """Async context manager: yields (browser_context, page) ready to use, with the
    PAX Store admin loaded (login performed if needed). Saves fresh session
    back to Supabase. Closes the browser on exit.

    Reads `PAX_USERNAME` / `PAX_PASSWORD` from environment.
    """
    user = os.environ["PAX_USERNAME"]
    pw = os.environ["PAX_PASSWORD"]
    saved = None
    with contextlib.suppress(Exception):
        saved = load_session(SESSION_KEY)
        if saved:
            print(f"→ loaded session from Supabase ({SESSION_KEY})")

    async with async_playwright() as pw_ctx:
        browser = await pw_ctx.chromium.launch(headless=headless)
        try:
            ctx = await browser.new_context(
                viewport=viewport or {"width": 1440, "height": 1000},
                storage_state=saved if saved else None,
            )
            page = await ctx.new_page()
            page.set_default_timeout(20000)
            try:
                fresh = await login_if_needed(page, user, pw)
            except Exception:  # noqa: BLE001
                # Session may have been kicked by another login; clear and retry once
                with contextlib.suppress(Exception):
                    delete_session(SESSION_KEY)
                ctx = await browser.new_context(viewport=viewport or {"width": 1440, "height": 1000})
                page = await ctx.new_page()
                page.set_default_timeout(20000)
                fresh = await login_if_needed(page, user, pw)
            if fresh:
                with contextlib.suppress(Exception):
                    save_session(SESSION_KEY, await ctx.storage_state())
                    print("→ saved fresh session to Supabase")
            yield ctx, page
        finally:
            await browser.close()


# ──────────────────────────────────────────────────────────────────────────────
# Navigation
# ──────────────────────────────────────────────────────────────────────────────

async def open_terminal(page: Page, serial: str, merchant_mid: str | None = None) -> None:
    """Terminal Management → (filter by merchant if given) → click row matching serial."""
    print(f"→ Terminal Management → SN={serial}")
    await page.locator("#left_menu_terminal_management").click()
    await page.wait_for_timeout(2500)
    await dismiss_cookies(page)

    if merchant_mid:
        try:
            await page.locator(f"text={merchant_mid}").first.click(timeout=5000)
            await page.wait_for_timeout(2000)
            print(f"  filtered by merchant {merchant_mid}")
        except Exception as exc:  # noqa: BLE001
            print(f"  merchant filter failed: {exc}")

    for selector in [
        f"a >> text=\"{serial}\"",
        f"text=\"{serial}\"",
        f"tr:has(td:text-is(\"{serial}\"))",
    ]:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                await loc.scroll_into_view_if_needed(timeout=3000)
                await loc.click(timeout=5000)
                print(f"  clicked exact-match {selector}")
                break
        except Exception:  # noqa: BLE001
            continue
    else:
        raise RuntimeError(f"Failed to locate terminal SN={serial} in list")
    await page.wait_for_timeout(2500)


__all__ = [
    "ADMIN_URL",
    "LOGIN_URL",
    "SESSION_KEY",
    "BrowserContext",
    "dismiss_cookies",
    "launch_session",
    "login_if_needed",
    "open_terminal",
    "shot",
]
