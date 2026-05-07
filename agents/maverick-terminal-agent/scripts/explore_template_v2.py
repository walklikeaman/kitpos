"""
explore_template_v2.py — read-only navigation through the Edit Parameter tabs.

Goal: understand the structure of TSYS / RECEIPT / POS / etc. tabs in the
new PAX UI. Does NOT change any data — only navigates and takes screenshots.

Flow:
    Terminal → Push Task → App → click BroadPOS task → Stage 3 (or 2)
    → if Stage 3: click PREVIOUS to enter Edit Parameter (Stage 2)
    → click each parameter tab in turn, screenshot each
    → dump field structure (input IDs, labels) for each tab
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

from maverick_agent.services.session_store import (  # noqa: E402
    load_session,
    save_session,
)

load_dotenv(PROJECT_ROOT / ".env")

ADMIN_URL = "https://paxus.paxstore.us/admin/"
SESSION_KEY = "paxstore"
DEBUG_DIR = PROJECT_ROOT / "tmp" / "ui-debug" / "explore"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


PARAMETER_TABS = [
    "INDUSTRY", "EDC", "RECEIPT", "TIP", "MISC", "TSYS", "COMMUNICATION",
    "CARD TYPE", "BIN FILE", "EMV", "EXTERNAL DEVICE", "POS", "MULTI-MERCHANT",
]


async def shot(page: Page, name: str) -> None:
    try:
        await page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  [shot {name} failed: {exc}]")


async def dismiss_cookies(page: Page) -> None:
    for label in ["NO, THANKS", "No, thanks"]:
        try:
            btn = page.locator(f"button:has-text('{label}')").first
            if await btn.count() > 0:
                await btn.click(timeout=3000)
                return
        except Exception:  # noqa: BLE001
            continue


async def login_if_needed(page: Page, user: str, pw: str) -> bool:
    await page.goto(ADMIN_URL, wait_until="domcontentloaded", timeout=20000)
    try:
        await page.wait_for_selector(
            "#left_menu_terminal_management, input[name='username'], input[type='password']",
            timeout=15000,
        )
    except Exception:  # noqa: BLE001
        pass
    await page.wait_for_timeout(1500)
    if "passport" in page.url.lower() or "auth.paxstore" in page.url.lower():
        print("→ logging in")
        await page.locator("input[name='username'], input[type='text']").first.fill(user, timeout=10000)
        await page.locator("input[name='password'], input[type='password']").first.fill(pw, timeout=10000)
        for sel in ["button[type='submit']", "button:has-text('Login')"]:
            try:
                await page.locator(sel).first.click(timeout=4000)
                break
            except Exception:  # noqa: BLE001
                continue
        await page.wait_for_url("**/admin/**", timeout=30000)
        await page.wait_for_selector("#left_menu_terminal_management", timeout=20000)
        return True
    return False


async def open_terminal(page: Page, serial: str, merchant_mid: str) -> None:
    print(f"→ Terminal Management → SN={serial}")
    await page.locator("#left_menu_terminal_management").click()
    await page.wait_for_timeout(2500)
    await dismiss_cookies(page)
    try:
        await page.locator(f"text={merchant_mid}").first.click(timeout=5000)
        await page.wait_for_timeout(2000)
    except Exception:  # noqa: BLE001
        pass
    for selector in [f"a >> text=\"{serial}\"", f"text=\"{serial}\""]:
        try:
            await page.locator(selector).first.click(timeout=5000)
            break
        except Exception:  # noqa: BLE001
            continue
    await page.wait_for_timeout(2500)


async def open_broadpos_task(page: Page) -> None:
    print("→ Push Task → App → click BroadPOS task")
    await page.locator("[role='tab']:has-text('Push Task')").first.click(timeout=10000)
    await page.wait_for_timeout(2500)
    # Click App sub-tab (exact text match to avoid 'App List' in sidebar)
    candidates = page.locator("button, [role='tab']")
    cnt = await candidates.count()
    for i in range(min(cnt, 200)):
        try:
            txt = (await candidates.nth(i).inner_text()).strip()
            if txt == "App":
                await candidates.nth(i).click(timeout=4000)
                break
        except Exception:  # noqa: BLE001
            continue
    await page.wait_for_timeout(2000)
    # Click into BroadPOS card
    for tag in ["span", "a", "div"]:
        loc = page.locator(f"{tag}:has-text('BroadPOS TSYS Sierra')").first
        if await loc.count() > 0:
            try:
                await loc.click(timeout=4000)
                print(f"  clicked {tag}:has-text('BroadPOS TSYS Sierra')")
                break
            except Exception:  # noqa: BLE001
                continue
    await page.wait_for_timeout(3000)
    await shot(page, "00-after-click-broadpos")


async def detect_stage(page: Page) -> str:
    """Inner-text scan for visible buttons. Avoids case-sensitivity issues."""
    candidates = page.locator("button")
    cnt = await candidates.count()
    seen = set()
    for i in range(min(cnt, 200)):
        try:
            btn = candidates.nth(i)
            if not await btn.is_visible():
                continue
            txt = (await btn.inner_text()).strip().upper()
            seen.add(txt)
        except Exception:  # noqa: BLE001
            continue
    if "ACTIVATE" in seen:
        return "active-task"
    if "NEXT" in seen:
        return "edit-parameter"
    return f"unknown (visible buttons: {sorted(seen)[:15]})"


async def go_to_edit_parameter(page: Page) -> None:
    """If we landed on Stage 3, click PREVIOUS to go back to Edit Parameter."""
    stage = await detect_stage(page)
    print(f"  current stage = {stage}")
    if stage == "active-task":
        print("  clicking PREVIOUS to go back to Stage 2 (Edit Parameter)")
        # Use inner_text scan
        candidates = page.locator("button")
        cnt = await candidates.count()
        clicked = False
        for i in range(min(cnt, 200)):
            try:
                btn = candidates.nth(i)
                if not await btn.is_visible():
                    continue
                txt = (await btn.inner_text()).strip().upper()
                if txt == "PREVIOUS":
                    await btn.click(timeout=5000)
                    clicked = True
                    break
            except Exception:  # noqa: BLE001
                continue
        if not clicked:
            print("  ⚠️ PREVIOUS button not found")
            return
        await page.wait_for_timeout(3500)
        await shot(page, "01-after-previous")
        new_stage = await detect_stage(page)
        print(f"  stage after PREVIOUS = {new_stage}")


async def click_tab_by_text(page: Page, label: str) -> bool:
    """Click a parameter tab button by exact text match. Returns True if clicked."""
    candidates = page.locator("button")
    cnt = await candidates.count()
    for i in range(min(cnt, 200)):
        try:
            txt = (await candidates.nth(i).inner_text()).strip()
            if txt == label:
                # Make sure it's not the left-sidebar version
                # (visibility check is enough because sidebar items have different y)
                if not await candidates.nth(i).is_visible():
                    continue
                await candidates.nth(i).scroll_into_view_if_needed(timeout=2000)
                await candidates.nth(i).click(timeout=4000)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


async def dump_form_fields(page: Page) -> list[dict]:
    """Return a list of {id, type, label, value, placeholder} for visible inputs in the form area."""
    result = await page.evaluate("""() => {
        const inputs = document.querySelectorAll('input, textarea, select, [role="combobox"]');
        const out = [];
        for (const el of inputs) {
            // Skip hidden + sidebar-area inputs
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            if (rect.left < 280) continue;  // skip sidebar
            // Find associated label by id or aria-labelledby
            let labelText = '';
            if (el.id) {
                const lbl = document.querySelector(`label[for="${el.id}"]`);
                if (lbl) labelText = (lbl.innerText || '').trim();
            }
            if (!labelText && el.getAttribute('aria-label')) {
                labelText = el.getAttribute('aria-label');
            }
            if (!labelText) {
                // Walk up to find a sibling label
                let p = el.parentElement;
                for (let i = 0; i < 4 && p; i++) {
                    const lbl = p.querySelector('label, .MuiFormLabel-root');
                    if (lbl) {
                        labelText = (lbl.innerText || '').trim();
                        break;
                    }
                    p = p.parentElement;
                }
            }
            out.push({
                id: el.id || '',
                tag: el.tagName,
                type: el.type || '',
                name: el.name || '',
                label: labelText,
                placeholder: el.placeholder || '',
                value: (el.value || '').toString().slice(0, 80)
            });
            if (out.length >= 60) break;
        }
        return out;
    }""")
    return result


async def explore_each_tab(page: Page) -> dict:
    """Click each parameter tab in turn and dump its fields."""
    tab_data: dict[str, list[dict]] = {}
    for tab in PARAMETER_TABS:
        print(f"→ exploring tab: {tab}")
        clicked = await click_tab_by_text(page, tab)
        if not clicked:
            print(f"  ⚠️ tab '{tab}' button not found/visible")
            tab_data[tab] = [{"error": "tab not found"}]
            continue
        await page.wait_for_timeout(1500)
        # Expand collapsed accordion sections. Try multiple selector strategies
        # since MUI / custom React components vary.
        for sel in [
            "[aria-expanded='false']",
            ".MuiAccordionSummary-root[aria-expanded='false']",
            "div[role='button'][aria-expanded='false']",
            ".MuiAccordion-root:not(.Mui-expanded) .MuiAccordionSummary-root",
        ]:
            try:
                els = page.locator(sel)
                n = await els.count()
                for j in range(n):
                    try:
                        if await els.nth(j).is_visible():
                            await els.nth(j).scroll_into_view_if_needed(timeout=1500)
                            await els.nth(j).click(timeout=2000)
                            await page.wait_for_timeout(400)
                    except Exception:  # noqa: BLE001
                        continue
            except Exception:  # noqa: BLE001
                continue
        # Also click on any text matching "INFORMATION" header (these are often
        # custom collapsibles, not MUI accordions).
        for header_text in ["POS INFORMATION", "MERCHANT PARAMETERS", "HOST URLS AND HOST PHONES"]:
            try:
                hdr = page.locator(f"text='{header_text}'").first
                if await hdr.count() > 0 and await hdr.is_visible():
                    await hdr.click(timeout=2000)
                    await page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                continue
        await page.wait_for_timeout(800)
        await shot(page, f"tab-{tab.replace(' ', '-')}")
        fields = await dump_form_fields(page)
        # Also dump radios / switches / select buttons for this tab
        toggles = await page.evaluate("""() => {
            const sel = 'input[type="radio"], input[type="checkbox"], .MuiSwitch-root, .MuiToggleButton-root, [role="switch"], [role="radio"]';
            return Array.from(document.querySelectorAll(sel))
                .filter(e => {
                    const r = e.getBoundingClientRect();
                    return r.width > 0 && r.left > 280;
                })
                .slice(0, 30)
                .map(e => ({
                    tag: e.tagName,
                    type: e.type || '',
                    name: e.name || '',
                    value: e.value || '',
                    checked: e.checked,
                    ariaLabel: e.getAttribute('aria-label') || '',
                    nearby: (e.closest('label, .MuiFormControlLabel-root')?.innerText || '').trim().slice(0, 60)
                }));
        }""")
        tab_data[tab] = {"fields": fields, "toggles": toggles}
        print(f"  found {len(fields)} fields, {len(toggles)} toggles")
    return tab_data


async def main() -> int:
    user = os.environ["PAX_USERNAME"]
    pw = os.environ["PAX_PASSWORD"]

    saved = None
    try:
        saved = load_session(SESSION_KEY)
    except Exception:  # noqa: BLE001
        pass

    async with async_playwright() as pw_ctx:
        browser = await pw_ctx.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 1000},
                storage_state=saved if saved else None,
            )
            page = await ctx.new_page()
            page.set_default_timeout(20000)
            fresh = await login_if_needed(page, user, pw)
            if fresh:
                try:
                    save_session(SESSION_KEY, await ctx.storage_state())
                except Exception:  # noqa: BLE001
                    pass

            await open_terminal(page, "1240490019", "201100308288")
            await open_broadpos_task(page)
            await go_to_edit_parameter(page)
            tab_data = await explore_each_tab(page)

            out_path = DEBUG_DIR / "tab_fields_summary.json"
            out_path.write_text(json.dumps(tab_data, indent=2), encoding="utf-8")
            print(f"\n✅ tab field summary → {out_path}")
            print(f"📁 screenshots → {DEBUG_DIR}")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"❌ FAILED: {exc}")
            try:
                await page.screenshot(path=str(DEBUG_DIR / "FAIL.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
            return 1
        finally:
            await browser.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
