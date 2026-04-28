"""
Cart flow test — adds 3 specific items to cart, selects existing address,
proceeds to checkout, takes screenshot. Does NOT place the order.

Usage:
  python3 test_cart_flow.py
"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from browser.amazon_session import amazon_browser_session

EMAIL    = os.getenv("AMAZON_BUSINESS_EMAIL", "")
PASSWORD = os.getenv("AMAZON_PASSWORD", "")

# Products from the order message
ITEMS = [
    {"asin": "B087CSV7NL", "title": "Scanner",    "qty": 1},
    {"asin": "B09GCR1VYL", "title": "Printer",     "qty": 1},
    {"asin": "B01LQL11BI", "title": "Cash Drawer", "qty": 1},
]

TARGET_ZIP  = "73703"
TARGET_NAME = "Lit Tobacco and Vape"
SESSION_FILE = "amazon_session.json"


async def add_via_product_page(p, asin: str, qty: int, name: str) -> bool:
    """Navigate to product page, click Add to Cart, navigate away. Returns True if button found."""
    await p.goto(f"https://www.amazon.com/dp/{asin}", wait_until="domcontentloaded", timeout=30_000)
    await p.wait_for_timeout(1_500)

    # Set qty if needed
    if qty > 1:
        try:
            qty_el = await p.query_selector("#quantity")
            if qty_el and await qty_el.is_visible():
                await qty_el.select_option(str(qty))
        except Exception:
            pass

    # Click Add to Cart
    for sel in [
        "#add-to-cart-button",
        "input[name='submit.add-to-cart']",
        "#submit.add-to-cart-ubb-announce",
        "input[id*='add-to-cart']",
        "button[id*='add-to-cart']",
    ]:
        try:
            loc = p.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click(timeout=5_000)
                await p.wait_for_timeout(2_000)
                print(f"    Clicked {sel} for {name}")
                # Navigate away immediately — item is in cart regardless of modal
                return True
        except Exception:
            pass

    # JS fallback
    result = await p.evaluate("""() => {
        const btn = document.getElementById('add-to-cart-button') ||
                    document.querySelector('[name="submit.add-to-cart"]') ||
                    document.querySelector('[id*="add-to-cart"]');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    if result:
        await p.wait_for_timeout(2_000)
        print(f"    JS add-to-cart for {name}")
        return True

    await p.screenshot(path=f"/tmp/amazon_product_{asin}.png")
    print(f"    ✗ No ATC button — screenshot: /tmp/amazon_product_{asin}.png")
    return False


async def main():
    async with amazon_browser_session(headless=False, storage_state_path=SESSION_FILE) as (session, _):
        p = session._page

        # ── 1. Login ────────────────────────────────────────────────────
        print("→ Logging in...")
        await session.login(EMAIL, PASSWORD)

        # ── 2. Clear cart ────────────────────────────────────────────────
        print("\n→ Clearing cart...")
        await p.goto("https://www.amazon.com/gp/cart/view.html",
                     wait_until="domcontentloaded", timeout=20_000)
        await p.wait_for_timeout(1_000)

        # Dump ALL delete buttons on the page
        del_count = 0
        for _ in range(10):  # up to 10 items
            del_btns = await p.query_selector_all(
                "input[value='Delete'], "
                "[data-action='delete'], "
                ".sc-action-delete input, "
                "span[data-action='delete'] input, "
                "input[name*='delete']"
            )
            if not del_btns:
                break
            try:
                await del_btns[0].click()
                await p.wait_for_timeout(1_000)
                del_count += 1
            except Exception:
                break
        print(f"  Cleared {del_count} item(s)")

        # ── 3. Add via product page ──────────────────────────────────────
        print("\n→ Adding items to cart (via product pages)...")
        for item in ITEMS:
            asin = item["asin"]
            print(f"  {item['title']} ({asin})...")
            ok = await add_via_product_page(p, asin, item["qty"], item["title"])
            if ok:
                print(f"    ✓ Added")
            # Always navigate back to clean state before next item
            # (handles redirect to cart/checkout page after ATC)

        # ── 4. Check cart ────────────────────────────────────────────────
        print("\n→ Checking cart...")
        await p.goto("https://www.amazon.com/gp/cart/view.html",
                     wait_until="domcontentloaded", timeout=20_000)
        await p.wait_for_timeout(2_000)
        await p.screenshot(path="/tmp/amazon_cart.png")
        print("  Screenshot: /tmp/amazon_cart.png")

        # Dump all item titles visible
        title_els = await p.query_selector_all(
            ".sc-product-title, "
            "[class*='item-title'], "
            ".a-truncate-full, "
            ".sc-list-item-content span[class*='title']"
        )
        titles = []
        for el in title_els[:10]:
            try:
                t = (await el.inner_text()).strip()[:60]
                if t:
                    titles.append(t)
            except Exception:
                pass
        if titles:
            print(f"  Items in cart: {titles}")
        else:
            # Try counting rows
            rows = await p.query_selector_all(
                ".sc-list-item[data-asin], "
                "[data-asin].s-result-item, "
                ".sc-list-item-content"
            )
            print(f"  Cart rows found: {len(rows)}")

        # Dump all submit/checkout buttons on page for debugging
        print("  Scanning for checkout buttons...")
        for sel in ["input[type='submit']", "input[type='button']", "button", "a"]:
            els = await p.query_selector_all(sel)
            for el in els[:20]:
                try:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip()[:50]
                        val  = await el.get_attribute("value") or ""
                        nm   = await el.get_attribute("name") or ""
                        if any(kw in (text + val + nm).lower()
                               for kw in ["proceed", "checkout", "buy", "order"]):
                            idd = await el.get_attribute("id") or ""
                            print(f"    [{sel}] id='{idd}' name='{nm}' val='{val}' text='{text}'")
                except Exception:
                    pass

        # ── 5. Proceed to Checkout ───────────────────────────────────────
        print("\n→ Proceeding to checkout...")
        clicked = False

        # Try all known selectors
        for sel in [
            "[name='proceedToRetailCheckout']",
            "#sc-buy-box-ptc-button input",
            "input[value*='Proceed to checkout']",
            "input[value*='Proceed to Check']",
            "a:has-text('Proceed to checkout')",
            "[data-feature-id='proceed-to-checkout-action']",
            "input[class*='ptc']",
            "#hlb-ptc-btn-native",
        ]:
            try:
                loc = p.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click(timeout=6_000)
                    clicked = True
                    print(f"  Clicked: {sel}")
                    break
            except Exception:
                pass

        if not clicked:
            # JS comprehensive fallback
            result = await p.evaluate("""() => {
                // Try by name
                let el = document.querySelector('[name="proceedToRetailCheckout"]');
                if (el) { el.click(); return 'proceedToRetailCheckout'; }
                // Try all submit inputs
                for (const inp of document.querySelectorAll('input[type="submit"], input[type="button"]')) {
                    const v = (inp.value || '').toLowerCase();
                    if (v.includes('proceed') || v.includes('checkout')) {
                        inp.click(); return inp.value;
                    }
                }
                // Try all buttons
                for (const btn of document.querySelectorAll('button')) {
                    const t = (btn.innerText || '').toLowerCase();
                    if (t.includes('proceed') || t.includes('checkout')) {
                        btn.click(); return btn.innerText.trim();
                    }
                }
                // Try all links
                for (const a of document.querySelectorAll('a')) {
                    const t = (a.innerText || '').toLowerCase();
                    if (t.includes('proceed') || t.includes('checkout')) {
                        a.click(); return a.innerText.trim();
                    }
                }
                return null;
            }""")
            if result:
                print(f"  JS checkout click: {result}")
                clicked = True

        if not clicked:
            # Navigate directly to Amazon Business checkout
            print("  No checkout button found — navigating directly to Business checkout...")
            await p.goto(
                "https://www.amazon.com/checkout/byg"
                "?experienceType=amazonBusiness",
                wait_until="domcontentloaded", timeout=20_000,
            )

        await p.wait_for_load_state("domcontentloaded", timeout=20_000)
        await p.wait_for_timeout(2_000)
        print(f"  URL after checkout: {p.url[:100]}")
        await p.screenshot(path="/tmp/amazon_after_checkout_click.png")

        # Handle "Need anything else?" upsell — click "Continue to checkout"
        body_text = await p.locator("body").inner_text()
        if "need anything else" in body_text.lower():
            print("  Upsell page detected — skipping...")
            dismissed = False
            for skip_sel in [
                "a:has-text('Continue to checkout')",
                "input[value*='Continue to checkout']",
                "button:has-text('Continue to checkout')",
                "a:has-text('No thanks')",
                "span:has-text('No thanks')",
                "button:has-text('No thanks')",
            ]:
                try:
                    loc = p.locator(skip_sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        print(f"  Clicking: {skip_sel}")
                        await loc.first.click()
                        await p.wait_for_load_state("domcontentloaded", timeout=15_000)
                        await p.wait_for_timeout(2_000)
                        dismissed = True
                        break
                except Exception:
                    pass
            if not dismissed:
                # JS fallback — find "Continue to checkout" link
                await p.evaluate("""() => {
                    for (const a of document.querySelectorAll('a')) {
                        if ((a.innerText || '').toLowerCase().includes('continue to checkout')) {
                            a.click(); return;
                        }
                    }
                }""")
                await p.wait_for_load_state("domcontentloaded", timeout=15_000)
                await p.wait_for_timeout(2_000)
            print(f"  URL after upsell: {p.url[:100]}")

        await p.wait_for_timeout(2_000)
        print(f"  URL: {p.url[:100]}")

        # ── 6. Select address ────────────────────────────────────────────
        print(f"\n→ Selecting address ZIP {TARGET_ZIP}...")
        await p.screenshot(path="/tmp/amazon_checkout_addr.png")

        addr_found = False

        # Strategy A: radio buttons
        for radio in await p.query_selector_all("input[type='radio']"):
            try:
                parent = await radio.evaluate_handle(
                    "el => el.closest('.a-box, .address-book-entry, [class*=\"address\"], tr, li')"
                )
                if parent:
                    txt = await parent.as_element().inner_text()
                    if TARGET_ZIP in txt or TARGET_NAME.lower() in txt.lower():
                        await radio.click()
                        await p.wait_for_timeout(1_000)
                        addr_found = True
                        print(f"  ✓ Radio selected for {TARGET_ZIP}")
                        break
            except Exception:
                pass

        # Strategy B: "Deliver to this address" button near ZIP text
        if not addr_found:
            for el in await p.query_selector_all(f"*:has-text('{TARGET_ZIP}')"):
                try:
                    container = await el.evaluate_handle(
                        "el => el.closest('.a-box, [class*=\"address\"], .ship-to-section, tr')"
                    )
                    if container:
                        deliver_btn = await container.as_element().query_selector(
                            "input[type='submit'], button"
                        )
                        if deliver_btn and await deliver_btn.is_visible():
                            await deliver_btn.click()
                            await p.wait_for_timeout(1_500)
                            addr_found = True
                            print(f"  ✓ Deliver-here for {TARGET_ZIP}")
                            break
                except Exception:
                    pass

        if not addr_found:
            print(f"  ⚠ Address not auto-selected (check /tmp/amazon_checkout_addr.png)")

        await p.wait_for_timeout(2_000)

        # ── 7. Final screenshot ──────────────────────────────────────────
        await p.screenshot(path="/tmp/amazon_checkout.png")
        print(f"\n✓ DONE")
        print(f"  Cart:     /tmp/amazon_cart.png")
        print(f"  Checkout: /tmp/amazon_checkout.png")
        print(f"  URL: {p.url[:120]}")
        print("\n  *** ORDER NOT PLACED ***")

        await p.wait_for_timeout(10_000)


asyncio.run(main())
