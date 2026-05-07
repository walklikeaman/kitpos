"""Form fill helpers, parameter sub-tab navigation, stage detection.

The 2026 PAX Store admin UI uses Material-UI components. Helpers here are
deliberately defensive: scan visible buttons by inner_text rather than relying
on Playwright's text-is which is case-strict and sometimes silently misses.
"""
from __future__ import annotations

from playwright.async_api import Page

from .browser import shot


# ──────────────────────────────────────────────────────────────────────────────
# Field fill primitives
# ──────────────────────────────────────────────────────────────────────────────

async def fill_text_by_id(page: Page, field_id: str, value: str, label: str) -> None:
    """Fill a text input by element id. No-op if value is empty.

    Playwright .fill() is idempotent (clears, then types), so re-runs on the
    same form are safe.
    """
    if not value:
        print(f"  {label}: SKIP (empty value)")
        return
    loc = page.locator(f'[id="{field_id}"]')
    try:
        await loc.fill(value, timeout=8000)
        print(f"  {label} = {value}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️ {label} fill failed: {exc}")


async def fill_autocomplete(
    page: Page, field_id: str, query: str, exact_option: str, label: str
) -> None:
    """Click an autocomplete input, type a query, click the matching option.

    Used for State / Time Zone / Country Code dropdowns where the visible options
    are rendered in a popper attached to body, not inside the dialog.
    """
    loc = page.locator(f'[id="{field_id}"]')
    try:
        await loc.click(timeout=5000)
        await loc.fill(query, timeout=8000)
        await page.wait_for_timeout(800)
        opt = page.get_by_text(exact_option, exact=True).first
        if await opt.count() == 0:
            opt = page.locator(
                f"li[role='option']:text-is('{exact_option}'),"
                f" .MuiAutocomplete-option:text-is('{exact_option}')"
            ).first
        await opt.click(timeout=5000)
        print(f"  {label} = {exact_option}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️ {label} autocomplete failed: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Tab navigation (parameter editor sub-tabs)
# ──────────────────────────────────────────────────────────────────────────────

async def click_tab_exact(page: Page, label: str, *, max_scan: int = 200) -> None:
    """Click a parameter tab button by its exact inner_text.

    Skips invisible matches (e.g. left-sidebar items with similar names like
    "App List" / "Firmware List").
    """
    candidates = page.locator("button")
    cnt = await candidates.count()
    for i in range(min(cnt, max_scan)):
        try:
            btn = candidates.nth(i)
            if not await btn.is_visible():
                continue
            txt = (await btn.inner_text()).strip()
            if txt == label:
                await btn.scroll_into_view_if_needed(timeout=2000)
                await btn.click(timeout=4000)
                await page.wait_for_timeout(1500)
                return
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError(f"Tab '{label}' not found / visible")


# ──────────────────────────────────────────────────────────────────────────────
# Stage detection + NEXT advancement
# ──────────────────────────────────────────────────────────────────────────────

async def detect_stage(page: Page) -> str:
    """Return the current Push Task Configuration stage based on visible buttons.

    Returns one of:
      - 'active-task'    — Stage 3, ACTIVATE button visible (terminal state)
      - 'edit-parameter' — Stage 2, NEXT button visible (parameter editor)
      - 'unknown (...)'  — neither found; includes the visible-button list to debug
    """
    candidates = page.locator("button")
    cnt = await candidates.count()
    seen: set[str] = set()
    for i in range(min(cnt, 200)):
        try:
            btn = candidates.nth(i)
            if not await btn.is_visible():
                continue
            seen.add((await btn.inner_text()).strip().upper())
        except Exception:  # noqa: BLE001
            continue
    if "ACTIVATE" in seen:
        return "active-task"
    if "NEXT" in seen:
        return "edit-parameter"
    return f"unknown (visible buttons: {sorted(seen)[:15]})"


async def click_next_once(page: Page) -> bool:
    """Click the bottom-of-form NEXT button.

    PAX has multiple NEXT-like buttons sometimes (paginators); the action button
    is the LAST visible one in DOM order. Returns True if clicked.
    """
    # Scroll to bottom so the action buttons are guaranteed in viewport.
    try:
        await page.keyboard.press("End")
        await page.wait_for_timeout(400)
    except Exception:  # noqa: BLE001
        pass

    candidates = page.locator("button")
    cnt = await candidates.count()
    found_indices: list[int] = []
    for i in range(cnt):
        try:
            btn = candidates.nth(i)
            if not await btn.is_visible():
                continue
            txt = (await btn.inner_text()).strip()
            if txt == "NEXT":
                found_indices.append(i)
        except Exception:  # noqa: BLE001
            continue
    if not found_indices:
        return False
    last_idx = found_indices[-1]
    try:
        target = candidates.nth(last_idx)
        await target.scroll_into_view_if_needed(timeout=3000)
        await target.click(timeout=5000)
        return True
    except Exception:  # noqa: BLE001
        return False


async def advance_until_active_task(
    page: Page, *, max_clicks: int = 15, debug_prefix: str = "next"
) -> None:
    """Click NEXT in a loop until ACTIVATE appears. Never clicks ACTIVATE itself.

    Tracks state on each iteration and stops as soon as we land on stage 3.
    Raises if max_clicks exceeded without reaching active-task stage.

    NOTE: as of 2026-05-07 this is **not yet verified end-to-end**. The script's
    NEXT clicks did not advance the form in testing (operator advanced manually
    with the same button). See PAXSTORE_AUTOMATION_V2.md "Open problem" section.
    """
    for i in range(1, max_clicks + 1):
        stage = await detect_stage(page)
        print(f"  iter #{i}: stage={stage}")
        if stage == "active-task":
            await shot(page, f"{debug_prefix}-stage3-final")
            print("✅ reached Stage 3 (Active Task) — NOT activating")
            return
        if not stage.startswith("edit-parameter"):
            await shot(page, f"{debug_prefix}-unknown-{i}")
            raise RuntimeError(f"Unexpected page state at iter #{i}: stage={stage}")
        if not await click_next_once(page):
            raise RuntimeError(f"NEXT button missing at iter #{i}")
        await page.wait_for_timeout(2500)
        await shot(page, f"{debug_prefix}-after-{i}")
    raise RuntimeError(f"Did not reach active-task stage after {max_clicks} clicks")


__all__ = [
    "advance_until_active_task",
    "click_next_once",
    "click_tab_exact",
    "detect_stage",
    "fill_autocomplete",
    "fill_text_by_id",
]
