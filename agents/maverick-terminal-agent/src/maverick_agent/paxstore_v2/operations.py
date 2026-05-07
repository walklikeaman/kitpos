"""High-level provisioning operations on the new PAX Store admin UI.

Each function takes a Playwright Page (assumed already logged in via
`browser.launch_session`) and performs ONE provisioning step.

To use multiple steps in sequence (e.g. provision-stand-alone), the orchestrator
keeps the Page open and calls these in order.
"""
from __future__ import annotations

from playwright.async_api import Page

from .browser import dismiss_cookies, shot
from .field_ids import (
    MISC_RUNNING_MODE_ID,
    RECEIPT_FIELD_IDS,
    TSYS_FIELD_IDS,
)
from .forms import (
    click_tab_exact,
    fill_autocomplete,
    fill_text_by_id,
    js_set_inputs,
)


# ──────────────────────────────────────────────────────────────────────────────
# Terminal creation
# ──────────────────────────────────────────────────────────────────────────────

async def create_terminal(
    page: Page,
    *,
    serial: str,
    model: str,
    merchant_mid: str,
    merchant_name: str,
    activate_immediately: bool = False,
) -> None:
    """Register a new terminal in PAX Store under a given merchant.

    Caller must have already navigated to /admin/. Uses the "+ TERMINAL" button
    (not the "Terminal Geo-Location" sidebar item — they share the substring).
    """
    print(f"→ creating terminal {model} SN={serial} for merchant {merchant_mid}")
    await page.locator("#left_menu_terminal_management").click()
    await page.wait_for_timeout(2500)
    await dismiss_cookies(page)
    try:
        await page.locator(f"text={merchant_mid}").first.click(timeout=5000)
        await page.wait_for_timeout(2000)
    except Exception as exc:  # noqa: BLE001
        print(f"  merchant filter failed: {exc}")
    await shot(page, "create-01-terminal-list")

    # Locate "+ TERMINAL" button (NOT the "Terminal Geo-Location" sidebar item).
    add_btn = None
    for sel in [
        "button:text-is('TERMINAL')",
        "button:text-is('+ TERMINAL')",
        "button:has-text('+ TERMINAL'):not(:has-text('Geo'))",
    ]:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            add_btn = loc
            break
    if add_btn is None:
        candidates = page.locator("button")
        cnt = await candidates.count()
        for i in range(cnt):
            try:
                txt = (await candidates.nth(i).inner_text()).strip()
                if txt in ("TERMINAL", "+ TERMINAL"):
                    add_btn = candidates.nth(i)
                    break
            except Exception:  # noqa: BLE001
                continue
    if add_btn is None:
        raise RuntimeError("'+ TERMINAL' button not found")
    await add_btn.click(timeout=10000)
    await page.wait_for_timeout(2500)
    await shot(page, "create-02-form")

    dialog = page.locator(".MuiDialog-root, [role='dialog']").last

    # Terminal Name
    name_value = f"{merchant_name} {serial}".strip() if merchant_name else f"Terminal {serial}"
    await dialog.get_by_label("Terminal Name", exact=True).fill(name_value, timeout=10000)
    print(f"  Terminal Name = {name_value}")

    # Activate Immediately (optional)
    if activate_immediately:
        try:
            await dialog.locator(
                "button:has-text('Immediately'), [role='button']:has-text('Immediately')"
            ).first.click(timeout=4000)
            print("  Activate = Immediately")
        except Exception:  # noqa: BLE001
            pass

    # Manufacturer + Model dropdowns
    async def pick_dropdown(label: str, value: str) -> None:
        trigger = dialog.locator(
            f"xpath=.//*[contains(normalize-space(text()),'{label}')]"
            f"/following::*[(self::div[contains(@class,'MuiSelect-select')]"
            f" or self::div[@role='button']"
            f" or contains(., 'Please Select'))][1]"
        ).first
        if await trigger.count() == 0:
            trigger = dialog.locator("text='Please Select'").nth(
                0 if label.lower() == "manufacturer" else 1
            )
        await trigger.click(timeout=10000)
        await page.wait_for_timeout(800)
        opt = page.locator(
            f"li[role='option']:text-is('{value}'),"
            f" li[role='option']:has-text('{value}'),"
            f" .MuiMenuItem-root:has-text('{value}')"
        ).first
        await opt.click(timeout=10000)
        await page.wait_for_timeout(500)
        print(f"  {label} = {value}")

    await pick_dropdown("Manufacturer", "PAX")
    await pick_dropdown("Model", model)

    # SN
    await dialog.get_by_label("SN", exact=True).fill(serial, timeout=10000)
    print(f"  SN = {serial}")
    await shot(page, "create-03-form-filled")

    # Click OK (in dialog, not page-level)
    ok_btn = page.locator(".MuiDialog-root button:has-text('OK')").last
    if await ok_btn.count() == 0:
        ok_btn = page.locator("button:has-text('OK')").last
    await ok_btn.click(timeout=10000)
    await page.wait_for_timeout(3000)
    await shot(page, "create-04-after-ok")
    print("✅ terminal created")


# ──────────────────────────────────────────────────────────────────────────────
# Push Task: open existing pending template task on a terminal
# ──────────────────────────────────────────────────────────────────────────────

async def open_pending_template_task(page: Page) -> None:
    """From Terminal Details, click into the pending BroadPOS Sierra task in App sub-tab."""
    print("→ Push Task → App → pending BroadPOS template task")
    await page.locator("[role='tab']:has-text('Push Task')").first.click(timeout=10000)
    await page.wait_for_timeout(2500)
    # App sub-tab (exact text — avoid "App List" sidebar item)
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
    # Click into BroadPOS Sierra card
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


# ──────────────────────────────────────────────────────────────────────────────
# Push Template (e.g. KIT-Android)
# ──────────────────────────────────────────────────────────────────────────────

async def push_template_to_terminal(page: Page, *, template_name: str = "KIT-Android") -> None:
    """On Terminal Details, push a parameter template via Push Task → +PUSH APP → Push Template."""
    print(f"→ Push Task → + PUSH APP → Push Template[{template_name}]")
    await page.locator("[role='tab']:has-text('Push Task')").first.click(timeout=10000)
    await page.wait_for_timeout(2000)

    # +PUSH APP (green pill button, top-right)
    push_btn = page.locator("button:has-text('PUSH APP')").first
    await push_btn.click(timeout=10000)
    await page.wait_for_timeout(2000)

    # Switch the modal to "Push Template" tab
    template_tab = (
        page.locator(".MuiDialog-root, [role='dialog']")
            .locator("button:has-text('Push Template'), [role='tab']:has-text('Push Template')")
            .first
    )
    if await template_tab.count() == 0:
        template_tab = page.locator("text='Push Template'").first
    await template_tab.click(timeout=10000)
    await page.wait_for_timeout(2000)

    # Check the row matching template_name
    row = page.locator(f"tr:has-text('{template_name}'), .el-table__row:has-text('{template_name}')").first
    checkbox = row.locator("input[type='checkbox'], .el-checkbox, .MuiCheckbox-root").first
    if await checkbox.count() == 0:
        await row.click(timeout=8000)
    else:
        await checkbox.click(timeout=8000)
    await page.wait_for_timeout(800)

    # OK
    ok_btn = page.locator("button:has-text('OK')").last
    await ok_btn.click(timeout=10000)
    await page.wait_for_timeout(3000)
    print("✅ template push submitted")


# ──────────────────────────────────────────────────────────────────────────────
# Push Firmware
# ──────────────────────────────────────────────────────────────────────────────

async def push_firmware_to_terminal(page: Page, *, firmware_name: str | None = None) -> None:
    """On Terminal Details, push firmware via Push Task → Firmware → +PUSH FIRMWARE.

    If firmware_name is None, picks the first (latest) row.
    """
    print("→ Push Task → Firmware → + PUSH FIRMWARE")
    await page.locator("[role='tab']:has-text('Push Task')").first.click(timeout=10000)
    await page.wait_for_timeout(2500)

    # Firmware sub-tab (exact-text scan; avoid 'Firmware List' sidebar item)
    candidates = page.locator("button, [role='tab']")
    cnt = await candidates.count()
    for i in range(min(cnt, 200)):
        try:
            btn = candidates.nth(i)
            if not await btn.is_visible():
                continue
            txt = (await btn.inner_text()).strip()
            if txt == "Firmware":
                await btn.click(timeout=4000)
                break
        except Exception:  # noqa: BLE001
            continue
    await page.wait_for_timeout(2000)

    # +PUSH FIRMWARE button — fall back to inner_text scan
    push_btn = None
    for sel in ["button:has-text('PUSH FIRMWARE')", "button:has-text('+ PUSH FIRMWARE')"]:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            push_btn = loc
            break
    if push_btn is None:
        cands = page.locator("button")
        n = await cands.count()
        for i in range(n):
            try:
                txt = (await cands.nth(i).inner_text()).strip()
                if txt in ("PUSH FIRMWARE", "+ PUSH FIRMWARE", "FIRMWARE"):
                    push_btn = cands.nth(i)
                    break
            except Exception:  # noqa: BLE001
                continue
    if push_btn is None:
        raise RuntimeError("'+ PUSH FIRMWARE' button not found")
    await push_btn.click(timeout=10000)
    await page.wait_for_timeout(2500)

    # Pick firmware row (radio button, NOT checkbox)
    dialog = page.locator(".MuiDialog-root, [role='dialog']").last
    if firmware_name:
        row = dialog.locator(f"tr:has-text('{firmware_name}'), .el-table__row:has-text('{firmware_name}')").first
    else:
        row = dialog.locator("tbody tr, .el-table__row").first
    radio = row.locator("input[type='radio'], .MuiRadio-root, .el-radio").first
    if await radio.count() == 0:
        radio = row.locator("td").first
    await radio.click(timeout=8000)
    await page.wait_for_timeout(800)

    # OK
    ok_btn = page.locator("button:has-text('OK')").last
    await ok_btn.click(timeout=10000)
    await page.wait_for_timeout(3500)
    print("✅ firmware push submitted")


# ──────────────────────────────────────────────────────────────────────────────
# TSYS / RECEIPT / MISC fills (parameter editor sub-tabs)
# ──────────────────────────────────────────────────────────────────────────────

async def fill_tsys_form(page: Page, var: dict) -> None:
    """Fill all TSYS sub-tab fields from a VAR row dict.

    Expects keys: dba, bin, agent_bank, chain, mid, store_number, terminal_number,
    city, state, zip, mcc, v_number (or terminal_id_number).

    Uses `js_set_inputs` to push all 11 plain text fields in ONE
    `page.evaluate()` call (verified 2026-05-08, see file-build-flow.md).
    Autocomplete fields (state, time_zone) still go through option-click
    because Material-UI keeps the selected-option state outside the <input>.
    """
    print("→ filling TSYS fields")
    await click_tab_exact(page, "TSYS")
    f = TSYS_FIELD_IDS
    tid_value = var.get("v_number", "").lstrip("V") or var.get("terminal_id_number", "")
    text_values: dict[str, str] = {
        f["merchant_name"]:   var.get("dba", ""),
        f["bin"]:             var.get("bin", ""),
        f["agent_number"]:    var.get("agent_bank", ""),
        f["chain_number"]:    var.get("chain", ""),
        f["mid"]:             var.get("mid", ""),
        f["store_number"]:    var.get("store_number", ""),
        f["terminal_number"]: var.get("terminal_number", ""),
        f["merchant_city"]:   var.get("city", ""),
        f["city_code"]:       var.get("zip", ""),
        f["category_code"]:   var.get("mcc", ""),
        f["tid"]:             tid_value,
    }
    await js_set_inputs(page, text_values, label="TSYS")
    state = var.get("state", "")
    if state:
        await fill_autocomplete(page, f["merchant_state"], state[:2], state, "Merchant State")
    await fill_autocomplete(page, f["time_zone"], "pst", "708-PST", "Time Zone")
    await shot(page, "tsys-filled")


async def fill_receipt_form(page: Page, merchant: dict) -> None:
    """Fill RECEIPT Header Lines from a merchant details dict.

    Expects keys: dba (or name), street, city, state, zip, phone.
    For stand-alone scenario only.

    Uses `js_set_inputs` to push all 4 header lines in one JS call.
    """
    print("→ filling RECEIPT fields (stand-alone)")
    await click_tab_exact(page, "RECEIPT")
    f = RECEIPT_FIELD_IDS
    dba = merchant.get("dba") or merchant.get("name", "")
    street = merchant.get("street", "")
    city = merchant.get("city", "")
    state = merchant.get("state", "")
    zipc = merchant.get("zip", "")
    line3 = ", ".join(p for p in [city, state, zipc] if p)
    phone = merchant.get("phone", "")
    await js_set_inputs(
        page,
        {
            f["header_1"]: dba,
            f["header_2"]: street,
            f["header_3"]: line3,
            f["header_4"]: phone,
        },
        label="RECEIPT",
    )
    await shot(page, "receipt-filled")


async def set_internal_pos_mode(page: Page) -> None:
    """Switch ECR-Terminal Integration Mode → 'Internal POS/Standalone' on MISC tab.

    Required for stand-alone scenario.
    """
    print("→ MISC tab: ECR-Terminal Integration Mode = Internal POS/Standalone")
    await click_tab_exact(page, "MISC")
    field = page.locator(f'[id="{MISC_RUNNING_MODE_ID}"]').first
    if await field.count() == 0:
        raise RuntimeError(f"runningMode field {MISC_RUNNING_MODE_ID} not found on MISC")
    await field.scroll_into_view_if_needed(timeout=3000)
    await field.click(timeout=5000)
    await page.wait_for_timeout(800)
    opt = page.get_by_text("Internal POS/Standalone", exact=True).first
    if await opt.count() == 0:
        opt = page.locator("li[role='option']:has-text('Internal POS/Standalone')").first
    await opt.click(timeout=5000)
    print("  ✓ Internal POS/Standalone selected")
    await shot(page, "misc-internal-pos")


# ──────────────────────────────────────────────────────────────────────────────
# Activate a pending task
# ──────────────────────────────────────────────────────────────────────────────

async def activate_pending_task(page: Page, *, kind: str = "firmware") -> None:
    """On Terminal Details, open a pending task in the given sub-tab and click ACTIVATE.

    kind: 'firmware' | 'app' | 'rki'
    """
    sub_label = {"firmware": "Firmware", "app": "App", "rki": "RKI"}[kind.lower()]
    print(f"→ Push Task → {sub_label} → activate pending task")
    await page.locator("[role='tab']:has-text('Push Task')").first.click(timeout=10000)
    await page.wait_for_timeout(2500)

    # Sub-tab
    candidates = page.locator("button, [role='tab']")
    cnt = await candidates.count()
    sub = None
    for i in range(min(cnt, 200)):
        try:
            txt = (await candidates.nth(i).inner_text()).strip()
            if txt == sub_label:
                sub = candidates.nth(i)
                break
        except Exception:  # noqa: BLE001
            continue
    if sub is None:
        raise RuntimeError(f"Sub-tab '{sub_label}' not found")
    await sub.click(timeout=10000)
    await page.wait_for_timeout(2000)
    await shot(page, f"act-01-{kind}-list")

    # Click into the pending task card. Cards aren't clickable as a whole;
    # the green firmware/app NAME inside the card is a link.
    name_keywords = {
        "firmware": ["PayDroid", "Taurus", "Cedar"],
        "app":      ["BroadPOS", "Sierra"],
        "rki":      ["RKI"],
    }[kind.lower()]
    clicked = False
    for kw in name_keywords:
        for tag in ["a", "span", "div"]:
            loc = page.locator(f"{tag}:has-text('{kw}')").first
            if await loc.count() > 0:
                try:
                    await loc.click(timeout=4000)
                    clicked = True
                    break
                except Exception:  # noqa: BLE001
                    continue
        if clicked:
            break
    if not clicked:
        raise RuntimeError(f"Could not click into pending {kind} task")
    await page.wait_for_timeout(2500)
    await shot(page, f"act-02-{kind}-task-config")

    # Click ACTIVATE
    activate_btn = None
    for sel in ["button:text-is('ACTIVATE')", "button:has-text('ACTIVATE')"]:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            activate_btn = loc
            break
    if activate_btn is None:
        raise RuntimeError("ACTIVATE button not found")
    await activate_btn.click(timeout=10000)
    await page.wait_for_timeout(2500)
    await shot(page, f"act-03-after-activate")
    # Some flows show a confirm modal
    try:
        confirm = page.locator(
            "button:has-text('OK'), button:has-text('CONFIRM'), button:has-text('YES')"
        ).last
        if await confirm.count() > 0:
            await confirm.click(timeout=4000)
            await page.wait_for_timeout(2500)
    except Exception:  # noqa: BLE001
        pass
    print(f"✅ {kind} task activated")


__all__ = [
    "activate_pending_task",
    "create_terminal",
    "fill_receipt_form",
    "fill_tsys_form",
    "open_pending_template_task",
    "push_firmware_to_terminal",
    "push_template_to_terminal",
    "set_internal_pos_mode",
]
