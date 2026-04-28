"""
Full merchant order flow.
- KIT Dashboard lookup (headless) → merchant address
- Amazon (visible browser): check address → smart cart sync → checkout

Usage:
  python3 test_merchant_order.py
"""
import asyncio
import re
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from kit.models import KitCredentials
from kit.merchant_lookup import MerchantLookupService
from browser.amazon_session import amazon_browser_session
from browser.address_manager import check_address_exists, add_address, set_delivery_address
from browser.cart_manager import sync_cart, get_cart_asins

KIT_EMAIL    = os.getenv("KIT_EMAIL", "")
KIT_PASSWORD = os.getenv("KIT_PASSWORD", "")
AMZ_EMAIL    = os.getenv("AMAZON_BUSINESS_EMAIL", "")
AMZ_PASSWORD = os.getenv("AMAZON_PASSWORD", "")

MERCHANT_ID = "201100306001"

# Items to order — all 4 ASINs confirmed from the Buy Again recording
ITEMS = [
    {"asin": "B087CSV7NL", "title": "Scanner (Symcode 2D)",              "qty": 1},
    {"asin": "B01LQL11BI", "title": "Cash Drawer (HK Systems 16in)",     "qty": 1},
    {"asin": "B09GCR1VYL", "title": "Printer (Volcora BT USB Black)",    "qty": 1},
    {"asin": "B0BMB9T82D", "title": "PIN Pad Stand (Hilipro Pax A35)",   "qty": 1},
]

SESSION_FILE = "amazon_session.json"
DEBUG_DIR    = Path("debug")


async def find_pin_pad_stand_asin(session) -> str | None:
    """Search order history for PAX / PIN pad stand ASIN."""
    # Try order history first (most reliable — matches what we actually buy)
    for query in ["PAX stand", "PIN pad stand", "terminal stand", "Lava stand", "pivot stand"]:
        print(f"  Searching order history: '{query}'...")
        history = await session.search_order_history(query)
        if history:
            best = history[0]
            print(f"  Found in history: {best['title'][:60]}  ASIN={best['asin']}")
            return best["asin"]

    # Fall back to regular search — specific terms for POS terminal stands
    for query in ["PAX A920 stand", "payment terminal stand countertop POS"]:
        print(f"  Searching Amazon: '{query}'...")
        results = await session.search_regular(query)
        if results:
            best = results[0]
            print(f"  Search result: {best['title'][:60]}  ASIN={best['asin']}")
            return best["asin"]

    return None


async def proceed_to_checkout(page) -> bool:
    """Click Proceed to Checkout, handle upsell page."""
    await page.goto("https://www.amazon.com/gp/cart/view.html",
                    wait_until="domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(1_500)

    clicked = False
    for sel in [
        "[name='proceedToRetailCheckout']",
        "#sc-buy-box-ptc-button input",
        "input[value*='Proceed to checkout']",
        "a:has-text('Proceed to checkout')",
        "[data-feature-id='proceed-to-checkout-action']",
    ]:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click(timeout=6_000)
                clicked = True
                print(f"  Clicked: {sel}")
                break
        except Exception:
            pass

    if not clicked:
        await page.evaluate("""() => {
            const el = document.querySelector('[name="proceedToRetailCheckout"]');
            if (el) { el.click(); return; }
            for (const inp of document.querySelectorAll('input[type="submit"]')) {
                if ((inp.value||'').toLowerCase().includes('proceed')) { inp.click(); return; }
            }
        }""")
        clicked = True

    await page.wait_for_load_state("domcontentloaded", timeout=20_000)
    await page.wait_for_timeout(2_000)

    # Handle "Need anything else?" upsell → Continue to checkout
    body = await page.locator("body").inner_text()
    if "need anything else" in body.lower():
        print("  Upsell → clicking Continue to checkout")
        for sel in [
            "a:has-text('Continue to checkout')",
            "button:has-text('Continue to checkout')",
        ]:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    await page.wait_for_timeout(2_000)
                    break
            except Exception:
                pass

    return clicked


async def main():
    # ── Step 1: KIT Dashboard (headless) ─────────────────────────────────
    print(f"{'='*60}")
    print(f"→ KIT Dashboard lookup — MID {MERCHANT_ID}")
    print(f"{'='*60}\n")

    kit_creds = KitCredentials(email=KIT_EMAIL, password=KIT_PASSWORD)
    service   = MerchantLookupService(kit_creds, headless=True, debug_dir=DEBUG_DIR)
    merchant  = await service.lookup_by_id(MERCHANT_ID)

    print(merchant.summary())

    if not merchant.address:
        print("\n⚠  No address in KIT Dashboard — cannot proceed.")
        return

    # Parse address parts
    addr = re.sub(r",?\s*USA?\s*$", "", merchant.address, flags=re.IGNORECASE).strip()

    zip_m    = re.search(r"\b(\d{5}(?:-\d{4})?)$", addr) or re.search(r"\b(\d{5}(?:-\d{4})?)\b", addr)
    zip_code = zip_m.group(1) if zip_m else ""
    state_m  = re.search(r"\b([A-Z]{2})[,\s]+\d{5}", addr)
    state    = state_m.group(1) if state_m else "OK"
    parts    = [p.strip() for p in addr.split(",")]
    street   = next((p for p in parts if re.match(r"^\d+", p)), parts[0] if parts else "")
    city     = ""
    for p in parts:
        p = p.strip()
        if p == street or p.upper() == state or re.match(r"^\d{5}", p):
            continue
        if re.match(r"^[A-Za-z ]+$", p) and len(p) > 1:
            city = p
            break

    principal = merchant.principal_name or ""
    biz_name  = merchant.merchant_name or ""
    if biz_name and principal:
        full_name = f"{biz_name} ({principal})"
    elif biz_name:
        full_name = biz_name
    else:
        full_name = principal or "Recipient"

    phone = merchant.phone or ""

    print(f"\nAmazon address form:")
    print(f"  Name:   {full_name}")
    print(f"  Phone:  {phone}")
    print(f"  Street: {street}")
    print(f"  City:   {city}")
    print(f"  State:  {state}  ZIP: {zip_code}")

    # ── Step 2: Amazon (visible browser) ─────────────────────────────────
    print(f"\n{'='*60}")
    print(f"→ Amazon Business flow")
    print(f"{'='*60}\n")

    async with amazon_browser_session(headless=False, storage_state_path=SESSION_FILE) as (session, _):
        p = session._page

        # Login
        print("→ Logging in...")
        await session.login(AMZ_EMAIL, AMZ_PASSWORD)

        # ── Address: check / add ──────────────────────────────────────────
        print(f"\n→ Checking address book for ZIP {zip_code}...")
        exists = await check_address_exists(p, zip_code, biz_name)

        if exists:
            print(f"  ✓ Address already in book")
        else:
            print(f"  Not found — adding...")
            await add_address(
                p,
                full_name=full_name,
                phone=phone,
                street=street,
                city=city,
                state=state,
                zip_code=zip_code,
            )

        # ── Smart cart sync ───────────────────────────────────────────────
        items = list(ITEMS)
        print(f"\n→ Syncing cart (wanted: {[i['title'] for i in items]})...")
        final_cart = await sync_cart(p, items)

        # Screenshot cart
        await p.goto("https://www.amazon.com/gp/cart/view.html",
                     wait_until="domcontentloaded", timeout=20_000)
        await p.wait_for_timeout(1_500)
        await p.screenshot(path="/tmp/amz_cart_final.png")
        print(f"\n  Cart screenshot: /tmp/amz_cart_final.png")

        # ── Set delivery address ──────────────────────────────────────────
        if zip_code:
            print(f"\n→ Setting delivery address ZIP {zip_code}...")
            await set_delivery_address(p, zip_code, biz_name)

        # ── Proceed to checkout ───────────────────────────────────────────
        print("\n→ Proceeding to checkout...")
        await proceed_to_checkout(p)

        await p.wait_for_timeout(2_000)
        await p.screenshot(path="/tmp/amz_checkout_final.png")

        print(f"\n{'='*60}")
        print(f"✓  DONE — cart has {len(final_cart)} item(s)")
        print(f"   Cart:     /tmp/amz_cart_final.png")
        print(f"   Checkout: /tmp/amz_checkout_final.png")
        print(f"   URL: {p.url[:100]}")
        print(f"{'='*60}")
        print(f"\n  *** ORDER NOT PLACED ***")

        await p.wait_for_timeout(8_000)


asyncio.run(main())
