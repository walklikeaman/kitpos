"""
Amazon address book manager.
Translated from Puppeteer recording → Playwright Python.

Provides:
  check_address_exists(page, zip_code, name_fragment) -> bool
  add_address(page, ...)                              -> None
  set_delivery_address(page, zip_code, name_fragment) -> bool
"""
from __future__ import annotations
import re


# ── State abbreviation → full name (for select_option fallback) ───────────────
_STATE_ABBR = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


async def check_address_exists(page, zip_code: str, name_fragment: str = "") -> bool:
    """
    Navigate to the Amazon address book and check whether an address
    matching zip_code (and optionally name_fragment) already exists.
    Returns True if found.
    """
    await page.goto("https://www.amazon.com/a/addresses", wait_until="domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(1_500)

    body = await page.locator("body").inner_text()
    zip_found = zip_code in body

    if zip_found and name_fragment:
        return name_fragment.lower() in body.lower()
    return zip_found


async def add_address(
    page,
    full_name: str,
    phone: str,
    street: str,
    city: str,
    state: str,          # 2-letter abbreviation, e.g. "OK"
    zip_code: str,
    apt_suite: str = "",
) -> None:
    """
    Add a new address via https://www.amazon.com/a/addresses/add.
    Translated directly from the 'Add new address in amazon.js' Puppeteer recording.
    """
    await page.goto(
        "https://www.amazon.com/a/addresses/add?ref=ya_address_book_add_button",
        wait_until="domcontentloaded", timeout=20_000,
    )
    await page.wait_for_timeout(1_500)

    # Full name
    name_field = page.locator("#address-ui-widgets-enterAddressFullName")
    await name_field.wait_for(state="visible", timeout=10_000)
    await name_field.triple_click()
    await name_field.fill(full_name)

    # Phone
    phone_field = page.locator("#address-ui-widgets-enterAddressPhoneNumber")
    await phone_field.click()
    await phone_field.triple_click()
    await phone_field.fill(phone)

    # Street address (line 1)
    street_field = page.locator("#address-ui-widgets-enterAddressLine1")
    await street_field.click()
    await street_field.triple_click()
    await street_field.fill(street)

    # Apt/suite (line 2) — optional
    if apt_suite:
        apt_field = page.locator("#address-ui-widgets-enterAddressLine2")
        await apt_field.click()
        await apt_field.fill(apt_suite)

    # City
    city_field = page.locator("#address-ui-widgets-enterAddressCity")
    await city_field.click()
    await city_field.triple_click()
    await city_field.fill(city)

    # State — try native select first, then styled dropdown
    state_upper = state.upper()
    state_full  = _STATE_ABBR.get(state_upper, state_upper)
    state_sel = "#address-ui-widgets-enterAddressStateOrRegion"
    state_set = False

    # Try as native <select>
    try:
        sel_el = await page.query_selector(f"{state_sel} select")
        if sel_el:
            await page.select_option(f"{state_sel} select", value=state_upper)
            state_set = True
    except Exception:
        pass

    if not state_set:
        # Styled dropdown — click the visible span, then type abbreviation + Enter
        try:
            dropdown_trigger = page.locator(f"{state_sel} > span > span, {state_sel} .a-dropdown-prompt")
            await dropdown_trigger.first.click()
            await page.wait_for_timeout(500)
            # Type abbreviation letters to filter
            for char in state_upper.lower():
                await page.keyboard.press(char)
                await page.wait_for_timeout(100)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(300)
            state_set = True
        except Exception:
            pass

    if not state_set:
        # Last resort — find option by text
        try:
            opt = page.locator(f"[id*='StateOrRegion'] option:has-text('{state_full}')")
            if await opt.count() > 0:
                val = await opt.first.get_attribute("value")
                await page.select_option(state_sel, value=val or state_upper)
        except Exception:
            pass

    # ZIP code
    zip_field = page.locator("#address-ui-widgets-enterAddressPostalCode")
    await zip_field.click()
    await zip_field.triple_click()
    await zip_field.fill(zip_code)

    # Country — default United States, but make sure it's selected
    try:
        country_sel = "#address-ui-widgets-countryCode"
        country_trigger = page.locator(f"{country_sel} > span > span")
        if await country_trigger.count() > 0:
            cur_text = (await country_trigger.first.inner_text()).strip()
            if "united states" not in cur_text.lower():
                await country_trigger.first.click()
                await page.wait_for_timeout(500)
                us_opt = page.locator(f"[id*='countryCode'] [id$='_232'], aria/United States[role='option']")
                if await us_opt.count() > 0:
                    await us_opt.first.click()
                    await page.wait_for_timeout(300)
    except Exception:
        pass

    # Submit — "Add address" button
    submit_btn = page.locator("#address-ui-widgets-form-submit-button span input")
    await submit_btn.wait_for(state="visible", timeout=10_000)
    await submit_btn.click()

    # Wait for success redirect → /a/addresses?alertId=yaab-enterAddressSucceed
    await page.wait_for_load_state("domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(1_500)

    if "alertId=yaab-enterAddressSucceed" in page.url or "/a/addresses" in page.url:
        print(f"  ✓ Address added: {full_name}, {street}, {city}, {state_upper} {zip_code}")
    else:
        # Check for inline errors
        error_els = await page.query_selector_all("[class*='error']:visible, .a-alert-content")
        errors = []
        for el in error_els[:3]:
            try:
                t = (await el.inner_text()).strip()
                if t:
                    errors.append(t)
            except Exception:
                pass
        if errors:
            raise RuntimeError(f"Address form errors: {errors}")
        print(f"  ✓ Address submitted (URL: {page.url[:80]})")


async def set_delivery_address(page, zip_code: str, name_fragment: str = "") -> bool:
    """
    Select delivery address from the cart-page location popup.
    Translated from 'Choose address.js' Puppeteer recording.

    Flow:
      1. Click glow-ingress (location widget in navbar)
      2. Click 'See all' to show full address list
      3. Find radio matching zip_code / name_fragment
      4. Click 'Done'

    Returns True if address was successfully selected.
    """
    # Click the location widget in the nav (line2 = zip/city, line1 = "Deliver to X")
    for ingress_sel in ["#glow-ingress-line2", "#glow-ingress-line1"]:
        try:
            loc = page.locator(ingress_sel)
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                await page.wait_for_timeout(1_500)
                break
        except Exception:
            pass

    # The popup should now be open — click "See all" to show all addresses
    see_all = page.locator("#GLUXMoreLink > a, a:has-text('See all')")
    try:
        if await see_all.count() > 0 and await see_all.first.is_visible():
            await see_all.first.click()
            await page.wait_for_timeout(1_500)
    except Exception:
        pass

    # Find the radio button in #GLUXAddressList matching our address
    addr_list = page.locator("#GLUXAddressList")
    found = False

    # First pass — match by aria-label (contains zip + name)
    radios = await page.query_selector_all("#GLUXAddressList input[type='radio']")
    for radio in radios:
        try:
            label = await radio.get_attribute("aria-label") or ""
            container = await radio.evaluate_handle(
                "el => el.closest('li, .a-list-item, span')"
            )
            container_text = ""
            if container:
                try:
                    container_text = await container.as_element().inner_text()
                except Exception:
                    pass

            combined = (label + " " + container_text).lower()
            zip_match  = zip_code in combined
            name_match = not name_fragment or name_fragment.lower() in combined

            if zip_match and name_match:
                await radio.click()
                found = True
                print(f"  ✓ Address radio selected: {label[:80] or container_text[:60]}")
                break
        except Exception:
            pass

    if not found:
        # Fallback — select any address containing the zip
        for radio in radios:
            try:
                label = await radio.get_attribute("aria-label") or ""
                if zip_code in label:
                    await radio.click()
                    found = True
                    print(f"  ✓ Address radio (zip fallback): {label[:80]}")
                    break
            except Exception:
                pass

    if not found:
        print(f"  ⚠ No address found for ZIP {zip_code} in popup")
        # Close popup
        for close_sel in ["button[aria-label='Close']", ".a-modal-close", "[data-action='a-modal-close']"]:
            try:
                cl = page.locator(close_sel)
                if await cl.count() > 0:
                    await cl.first.click()
                    break
            except Exception:
                pass
        return False

    # Click 'Done' button
    done_btn = page.locator("button:has-text('Done'), input[aria-labelledby*='done' i], [id*='done' i] input")
    # Also try the autoid pattern from recording
    done_fallbacks = [
        "button:has-text('Done')",
        "#GLUXConfirmClose",
        "span:has-text('Done') > input",
        "[aria-label='Done']",
    ]
    done_clicked = False
    for done_sel in done_fallbacks:
        try:
            loc = page.locator(done_sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click()
                done_clicked = True
                break
        except Exception:
            pass

    if not done_clicked:
        # JS click any visible "Done" button
        await page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button, input[type="submit"]')) {
                if ((btn.innerText || btn.value || '').trim().toLowerCase() === 'done') {
                    btn.click(); return;
                }
            }
        }""")

    await page.wait_for_load_state("domcontentloaded", timeout=15_000)
    await page.wait_for_timeout(2_000)
    print(f"  ✓ Delivery address set to ZIP {zip_code}")
    return True
