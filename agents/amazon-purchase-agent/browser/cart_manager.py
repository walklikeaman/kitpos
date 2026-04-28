"""
Smart cart manager — reads cart by ASIN, diffs against wanted list,
removes wrong items, adds missing ones, then verifies.
"""
from __future__ import annotations
import re


async def get_cart_asins(page) -> dict[str, dict]:
    """
    Return {asin: {title, qty}} for EVERY item in the cart.
    Covers main cart, Amazon Business 'Your Items', and any other section.
    Uses JS to scan all data-asin elements across the entire page.
    """
    await page.goto("https://www.amazon.com/gp/cart/view.html",
                    wait_until="domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(2_000)

    # JS scan — find every element with data-asin anywhere on page,
    # walk up to get a row container, extract title + qty
    raw = await page.evaluate("""() => {
        const result = {};

        // All elements that carry a data-asin on cart page
        const selectors = [
            '[data-asin].sc-list-item',
            '.sc-list-item[data-asin]',
            '[data-asin][class*="list-item"]',
            '[data-asin][class*="cart-item"]',
            // "Your Items" section uses different wrapper
            'div[data-item-asin]',
            '[data-asin]:not(script):not(input)',
        ];

        for (const sel of selectors) {
            for (const el of document.querySelectorAll(sel)) {
                const asin = el.getAttribute('data-asin') || el.getAttribute('data-item-asin') || '';
                if (!asin || asin.length < 10) continue;
                if (asin in result) continue;   // already found

                // Skip recommendation / upsell sections
                const section = el.closest('#soldByAmazon, #buyItAgain, .a-carousel-card');
                if (section) continue;

                // Title
                const titleEl = el.querySelector(
                    '.sc-product-title span, [class*="item-title"] span, ' +
                    '.a-truncate-full, [class*="product-title"] span, ' +
                    'a[href*="/dp/"] span'
                );
                const title = (titleEl ? titleEl.innerText : '').trim().slice(0, 60) || asin;

                // Quantity
                let qty = 1;
                const qtyInput = el.querySelector('input[id*="quantity"], input[name*="quantity"]');
                const qtySelect = el.querySelector('select[name*="qty"], select[name*="quantity"]');
                const qtySpan = el.querySelector(
                    'span.sc-item-quantity-count, [class*="quantity-label"], ' +
                    'span[aria-label*="Quantity"], .a-dropdown-prompt'
                );

                if (qtyInput) {
                    qty = parseInt(qtyInput.value) || 1;
                } else if (qtySelect) {
                    qty = parseInt(qtySelect.value) || 1;
                } else if (qtySpan) {
                    qty = parseInt(qtySpan.innerText.trim()) || 1;
                }

                result[asin] = { title, qty };
            }
        }
        return result;
    }""")

    return dict(raw)


async def delete_all_cart_items(page) -> int:
    """Delete ALL items from cart. Returns count removed."""
    removed = 0
    for _ in range(20):  # up to 20 items
        await page.goto("https://www.amazon.com/gp/cart/view.html",
                        wait_until="domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(1_000)

        # Find first delete button / link
        deleted = False
        for sel in [
            # Link with text "Delete"
            ".sc-action-delete input",
            "input[value='Delete']",
            "span[data-action='delete'] > span > input",
            # Newer Amazon cart: text link
            "a.sc-action-delete",
        ]:
            btns = await page.query_selector_all(sel)
            for btn in btns:
                try:
                    if await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(1_200)
                        removed += 1
                        deleted = True
                        break
                except Exception:
                    pass
            if deleted:
                break

        # JS fallback — click first visible "Delete" submit input or link
        if not deleted:
            clicked = await page.evaluate("""() => {
                for (const el of document.querySelectorAll('input[value="Delete"], a')) {
                    const txt = (el.value || el.innerText || '').trim();
                    if (txt === 'Delete') {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            if clicked:
                await page.wait_for_timeout(1_200)
                removed += 1
                deleted = True

        if not deleted:
            break  # Nothing left to delete

    return removed


async def set_item_quantity(page, asin: str, wanted_qty: int) -> bool:
    """
    Change quantity of an item already in cart.
    Uses the +/- buttons or the qty input field.
    """
    await page.goto("https://www.amazon.com/gp/cart/view.html",
                    wait_until="domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(1_000)

    # Find the cart row for this ASIN
    row = await page.query_selector(f"[data-asin='{asin}'].sc-list-item")
    if not row:
        return False

    # Try dropdown/select quantity input first
    qty_input = await row.query_selector("input[id*='quantity'], input[name*='quantity']")
    if qty_input:
        try:
            await qty_input.triple_click()
            await qty_input.fill(str(wanted_qty))
            await qty_input.press("Enter")
            await page.wait_for_timeout(1_500)
            return True
        except Exception:
            pass

    # Try select element (older Amazon cart)
    select_el = await row.query_selector("select[name*='asin.qty']")
    if select_el:
        try:
            await select_el.select_option(str(wanted_qty) if wanted_qty <= 10 else "10")
            await page.wait_for_timeout(1_500)
            return True
        except Exception:
            pass

    # Use +/- buttons
    qty_span = await row.query_selector("span.sc-item-quantity-count, [class*='quantity-label']")
    if qty_span:
        try:
            current = int((await qty_span.inner_text()).strip())
        except Exception:
            current = 1

        minus_btn = await row.query_selector("button[aria-label*='decrease'], button[aria-label*='minus']")
        plus_btn  = await row.query_selector("button[aria-label*='increase'], button[aria-label*='plus']")

        diff = wanted_qty - current
        btn = plus_btn if diff > 0 else minus_btn
        if btn:
            for _ in range(abs(diff)):
                await btn.click()
                await page.wait_for_timeout(500)
            return True

    return False


ORDER_HISTORY_URL = (
    "https://www.amazon.com/gp/css/order-history"
    "?ref_=abn_yadd_ad_your_orders"
    "#tab/yoOrdersTabination/pagination/1/"
)


async def add_from_order_history(page, asin: str, qty: int = 1, name: str = "") -> bool:
    """
    Add a previously purchased item to cart via the Order History
    "Buy it again" deep-link (translated from 'Add items from orders.js').

    Flow:
      1. Navigate to Order History (Orders tab)
      2. Scan every  a[href*="gp/buyagain"]  link on the page;
         decode the  ats=  base64 param — if it contains our ASIN, that is our link.
      3. Navigate to that filtered Buy Again URL
         → the page shows exactly one grid card: #gridElement-{ASIN}
      4. Click the Add-to-Cart input inside that card.
      5. Repeat from step 1 for qty > 1.

    Returns True if at least one click succeeded.
    """
    label = name or asin

    # JS that scans the page for a Buy-it-again href whose ats-decoded JSON
    # contains our ASIN, then returns the href (or null if not found).
    _FIND_BIA_LINK_JS = """(asin) => {
        for (const a of document.querySelectorAll('a[href*="gp/buyagain"]')) {
            const m = a.href.match(/[?&]ats=([^&]+)/);
            if (!m) continue;
            try {
                const decoded = atob(decodeURIComponent(m[1]));
                if (decoded.includes(asin)) return a.href;
            } catch(_) {}
        }
        return null;
    }"""

    added = 0
    for _ in range(max(qty, 1)):
        # ── Step 1: Order History page ──────────────────────────────────
        await page.goto(ORDER_HISTORY_URL,
                        wait_until="domcontentloaded", timeout=25_000)
        await page.wait_for_timeout(1_500)

        # Click "Orders" tab if not already on it
        orders_tab = page.locator("#tabHeading_yoOrdersTabination > a")
        try:
            if await orders_tab.count() > 0 and await orders_tab.is_visible():
                await orders_tab.click()
                await page.wait_for_timeout(1_000)
        except Exception:
            pass

        # ── Step 2: Find the "Buy it again" link for this ASIN ──────────
        bia_href: str | None = await page.evaluate(_FIND_BIA_LINK_JS, asin)

        if not bia_href:
            # Scroll down once and retry (older orders may be lower on page)
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(600)
            bia_href = await page.evaluate(_FIND_BIA_LINK_JS, asin)

        if not bia_href:
            print(f"    ⚠ Order History: no 'Buy it again' link found for {label} ({asin})")
            return False

        # ── Step 3: Navigate to filtered Buy Again page ─────────────────
        await page.goto(bia_href, wait_until="domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(1_500)

        # ── Step 4: Click ATC in #gridElement-{ASIN} ───────────────────
        grid = page.locator(f"#gridElement-{asin}")
        clicked = False

        # Small scroll to make sure card is in view
        try:
            if await grid.count() > 0:
                await grid.scroll_into_view_if_needed()
        except Exception:
            pass

        atc = grid.locator(
            "div.add-to-cart-data > div.celwidget input, input[type='submit']"
        ).first

        try:
            if await atc.count() > 0 and await atc.is_visible():
                await atc.click()
                await page.wait_for_timeout(1_000)
                clicked = True
        except Exception:
            pass

        if not clicked:
            # JS fallback
            clicked = await page.evaluate(f"""() => {{
                const grid = document.getElementById('gridElement-{asin}');
                if (!grid) return false;
                const btn = grid.querySelector(
                    'div.add-to-cart-data input, input[type="submit"]'
                );
                if (btn) {{ btn.click(); return true; }}
                return false;
            }}""")
            if clicked:
                await page.wait_for_timeout(1_000)

        if clicked:
            added += 1
        else:
            print(f"    ✗ Order History Buy Again: no ATC button for {label} ({asin})")
            break

    if added:
        print(f"    ✓ Order History Buy Again: {label} ({asin}) × {added}")
    return added > 0


async def add_from_buy_again(page, asin: str, qty: int = 1, name: str = "") -> bool:
    """
    Add a previously purchased item to cart via the Buy Again page
    (https://www.amazon.com/gp/buyagain).

    Flow (translated from 'Recuring order.js' Puppeteer recording):
      1. Navigate to /gp/buyagain
      2. Find #gridElement-{ASIN} on the page (scroll up to 3× if needed)
      3. Click the Add to Cart input inside that grid element
      4. Repeat for qty > 1 (Buy Again has no qty selector — re-click each time)

    Returns True if at least one click succeeded.
    """
    await page.goto("https://www.amazon.com/gp/buyagain",
                    wait_until="domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(1_500)

    # Scroll down up to 5 times looking for the grid element
    grid = page.locator(f"#gridElement-{asin}")
    found = False
    for _ in range(5):
        if await grid.count() > 0:
            found = True
            break
        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(600)

    if not found:
        label = name or asin
        print(f"    ⚠ Buy Again: {label} ({asin}) not on page")
        return False

    # Selector from recording: div.add-to-cart-data > div.celwidget input
    atc = grid.locator("div.add-to-cart-data > div.celwidget input, input[type='submit']").first

    added = 0
    for i in range(max(qty, 1)):
        try:
            if await atc.count() > 0 and await atc.is_visible():
                await atc.click()
                await page.wait_for_timeout(900)
                added += 1
            else:
                # JS fallback
                clicked = await page.evaluate(f"""() => {{
                    const grid = document.getElementById('gridElement-{asin}');
                    if (!grid) return false;
                    const btn = grid.querySelector(
                        'div.add-to-cart-data input, input[type="submit"]'
                    );
                    if (btn) {{ btn.click(); return true; }}
                    return false;
                }}""")
                if clicked:
                    await page.wait_for_timeout(900)
                    added += 1
                else:
                    break
        except Exception:
            break

    label = name or asin
    if added:
        print(f"    ✓ Buy Again: {label} ({asin}) × {added}")
    else:
        print(f"    ✗ Buy Again: could not click ATC for {label} ({asin})")
    return added > 0


async def add_to_cart_via_product_page(page, asin: str, qty: int, name: str) -> bool:
    """Navigate to product page, select qty if needed, click Add to Cart."""
    await page.goto(f"https://www.amazon.com/dp/{asin}",
                    wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(1_500)

    # Check for robot/captcha page
    title = await page.title()
    if "robot" in title.lower() or "captcha" in title.lower() or "sorry" in title.lower():
        print(f"    ⚠ Robot check on {asin} — taking screenshot")
        await page.screenshot(path=f"/tmp/robot_{asin}.png")
        return False

    # Set quantity dropdown if > 1
    if qty > 1:
        try:
            qty_el = await page.query_selector("#quantity")
            if qty_el and await qty_el.is_visible():
                await qty_el.select_option(str(qty) if qty <= 30 else "30")
                await page.wait_for_timeout(300)
        except Exception:
            pass

    # Find and click Add to Cart
    for sel in [
        "#add-to-cart-button",
        "input[name='submit.add-to-cart']",
        "#submit.add-to-cart-ubb-announce",
        "[data-feature-id='desktop-atc'] input[type='submit']",
        "[data-feature-id='desktop-atc'] button",
        "input[id*='add-to-cart']",
        "button[id*='add-to-cart']",
    ]:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click(timeout=5_000)
                await page.wait_for_timeout(2_500)
                return True
        except Exception:
            pass

    # JS fallback
    ok = await page.evaluate("""() => {
        const btn = document.getElementById('add-to-cart-button')
                 || document.querySelector('[name="submit.add-to-cart"]')
                 || document.querySelector('[id*="add-to-cart"]');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    if ok:
        await page.wait_for_timeout(2_500)
        return True

    await page.screenshot(path=f"/tmp/no_atc_{asin}.png")
    print(f"    ⚠ No ATC button — screenshot: /tmp/no_atc_{asin}.png")
    return False


async def sync_cart(
    page,
    wanted: list[dict],   # [{"asin": "...", "title": "...", "qty": 1}, ...]
) -> dict[str, dict]:
    """
    Ensure cart contains exactly the wanted items in the right quantities.
    1. Read current cart
    2. Delete items NOT in wanted list
    3. Fix quantities for existing items
    4. Add missing items
    5. Verify and return final cart state
    """
    wanted_map = {item["asin"]: item for item in wanted}

    # ── Step 1: Read current cart ─────────────────────────────────────
    current = await get_cart_asins(page)
    print(f"  Current cart: {list(current.keys()) or 'empty'}")

    # ── Step 2: Delete items not in wanted list ───────────────────────
    for asin in list(current.keys()):
        if asin not in wanted_map:
            print(f"  Removing unwanted item {asin} ({current[asin]['title'][:40]})...")
            await _delete_item_by_asin(page, asin)
            await page.wait_for_timeout(1_000)

    # Reload cart after deletions
    current = await get_cart_asins(page)

    # ── Step 3: Fix quantities for items already in cart ──────────────
    for asin, info in list(current.items()):   # list() — safe iteration
        if asin in wanted_map:
            wanted_qty = wanted_map[asin]["qty"]
            if info["qty"] != wanted_qty:
                print(f"  Fixing qty for {asin}: {info['qty']} → {wanted_qty}")
                ok = await set_item_quantity(page, asin, wanted_qty)
                if not ok:
                    print(f"    Could not set quantity — will delete and re-add")
                    await _delete_item_by_asin(page, asin)
                    current.pop(asin, None)
            else:
                print(f"  ✓ {info['title'][:40]} already in cart × {info['qty']}")

    # Reload after qty fixes
    current = await get_cart_asins(page)

    # ── Step 4: Add missing items ─────────────────────────────────────
    # Priority order (all use previously purchased items — no random search):
    #   1. Buy Again full page  (/gp/buyagain)
    #      Fast; works when the item appears in the Buy Again list.
    #   2. Order History "Buy it again" deep-link  (/gp/css/order-history)
    #      Reliable fallback — finds the item-specific filtered Buy Again URL
    #      by decoding the ats= base64 param on each order row link.
    #   3. Product page  (/dp/ASIN)
    #      Always works but slowest; higher robot-check risk.
    for asin, item in wanted_map.items():
        if asin not in current:
            print(f"  Adding {item['title']} ({asin}) × {item['qty']}...")

            ok = await add_from_buy_again(page, asin, item["qty"], item["title"])

            if not ok:
                print(f"    Buy Again list miss — trying Order History flow...")
                ok = await add_from_order_history(
                    page, asin, item["qty"], item["title"]
                )

            if not ok:
                print(f"    Order History miss — trying product page...")
                ok = await add_to_cart_via_product_page(
                    page, asin, item["qty"], item["title"]
                )

            if not ok:
                print(f"    ✗ All methods failed for {item['title']} ({asin})")

    # ── Step 5: Final verification ────────────────────────────────────
    await page.goto("https://www.amazon.com/gp/cart/view.html",
                    wait_until="domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(2_000)

    final = await get_cart_asins(page)
    print("\n  ── Final cart contents ──")
    all_ok = True
    for item in wanted:
        asin = item["asin"]
        if asin in final:
            qty_ok = final[asin]["qty"] == item["qty"]
            status = "✓" if qty_ok else f"✗ qty={final[asin]['qty']} (wanted {item['qty']})"
            print(f"  {status}  {item['title']} ({asin}) × {final[asin]['qty']}")
            if not qty_ok:
                all_ok = False
        else:
            print(f"  ✗ MISSING: {item['title']} ({asin})")
            all_ok = False

    extra = [a for a in final if a not in wanted_map]
    for a in extra:
        print(f"  ⚠ Extra item in cart: {a} ({final[a]['title'][:40]})")

    return final


async def _delete_item_by_asin(page, asin: str) -> bool:
    """Delete a specific item from cart by ASIN."""
    await page.goto("https://www.amazon.com/gp/cart/view.html",
                    wait_until="domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(800)

    row = await page.query_selector(f"[data-asin='{asin}'].sc-list-item")
    if not row:
        # Fallback: look for row containing asin text
        rows = await page.query_selector_all(".sc-list-item[data-asin]")
        for r in rows:
            a = await r.get_attribute("data-asin") or ""
            if a == asin:
                row = r
                break

    if not row:
        return False

    # Click delete within this row
    for sel in [
        ".sc-action-delete input",
        "input[value='Delete']",
        "span[data-action='delete'] input",
        "a.sc-action-delete",
    ]:
        try:
            btn = await row.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(1_200)
                return True
        except Exception:
            pass

    # JS fallback
    clicked = await page.evaluate(f"""() => {{
        const row = document.querySelector('[data-asin="{asin}"].sc-list-item');
        if (!row) return false;
        for (const el of row.querySelectorAll('input, a')) {{
            const txt = (el.value || el.innerText || '').trim();
            if (txt === 'Delete') {{ el.click(); return true; }}
        }}
        return false;
    }}""")
    if clicked:
        await page.wait_for_timeout(1_200)
    return clicked
