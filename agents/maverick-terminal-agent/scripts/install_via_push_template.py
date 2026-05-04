"""
Install BroadPOS TSYS Sierra via the Push Template flow.

Canonical procedure per `docs/PAXSTORE_PROVISIONING_RULES.md` §4:

    Terminal → Push Task → App → + PUSH APP
        → "Push Template" tab in dialog
        → tick the template row
        → OK

The template knows which app to install and which Parameter File to load —
do NOT search the app catalog by hand, do NOT pick BroadPOS TSYS Sierra by
name, do NOT touch the Model dropdown in App Detail.

After OK lands you on the parameter editor, call `fill_tsys_parameters()`
from `install_broadpos_app.py` (that helper is still valid) to populate the
TSYS tab from VAR data, then click NEXT.

Recorded selectors (from user-supplied `Template.js`):

    'aria/Add App'                                     # opens Push App dialog
    'aria/Push Template'                               # second tab
    'aria/[role="table"]', 'aria/[role="checkbox"]'    # template row checkbox
    'aria/OK'                                          # confirm
"""
from __future__ import annotations

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


# Selector ladder mirroring Template.js — try in order.
PUSH_APP_BUTTON_SELECTORS = [
    'button[aria-label="Add App"]',
    'div.layout_main_head_right button',
    'text=Push App',
]

PUSH_TEMPLATE_TAB_SELECTORS = [
    'div.MuiDialog-root button:has-text("Push Template")',
    'div.MuiDialog-root button:nth-of-type(2)',
]

TEMPLATE_ROW_CHECKBOX_SELECTORS = [
    'div.dialog_section_box input[type="checkbox"]',
    'div.MuiDialog-root tbody tr:first-of-type input[type="checkbox"]',
]

OK_BUTTON_SELECTORS = [
    'div.MuiDialog-root button:has-text("OK")',
    'div.MuiDialog-root span:nth-of-type(2) > button',
]


async def _click_first(page: Page, selectors: list[str], *, label: str) -> None:
    """Click the first selector that resolves to a visible element."""
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.is_visible(timeout=1500):
                await locator.click()
                return
        except PlaywrightTimeoutError:
            continue
    raise RuntimeError(f"Push Template flow: could not click {label!r} via {selectors!r}")


async def install_via_push_template(page: Page) -> None:
    """
    Drive the Push Template flow on the currently-open terminal page.

    Pre-condition: page is on Terminal Details → Push Task tab → App sub-tab.
    Post-condition: parameter editor is open for the chosen template's app.

    The caller is responsible for calling `fill_tsys_parameters()` and clicking
    NEXT afterwards.
    """
    await _click_first(page, PUSH_APP_BUTTON_SELECTORS, label="Push App")
    await page.wait_for_timeout(1500)

    await _click_first(page, PUSH_TEMPLATE_TAB_SELECTORS, label="Push Template tab")
    await page.wait_for_timeout(1500)

    await _click_first(page, TEMPLATE_ROW_CHECKBOX_SELECTORS, label="template row checkbox")
    await page.wait_for_timeout(500)

    await _click_first(page, OK_BUTTON_SELECTORS, label="OK")
    await page.wait_for_timeout(2500)


__all__ = ["install_via_push_template"]
