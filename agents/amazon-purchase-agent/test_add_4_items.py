"""
Add 4 POS items to Amazon cart — headless by default.

Usage:
  AMAZON_BUSINESS_EMAIL=you@example.com AMAZON_PASSWORD=secret python3 test_add_4_items.py
  # or with saved session:
  python3 test_add_4_items.py  (uses amazon_session.json if present)
"""
from __future__ import annotations
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

EMAIL    = os.getenv("AMAZON_BUSINESS_EMAIL", "")
PASSWORD = os.getenv("AMAZON_PASSWORD", "")
SESSION_FILE = "amazon_session.json"

# 4 items: confirmed ASINs from previous orders / pinned list
ITEMS = [
    {"asin": "B01LQL11BI", "title": "Cash Drawer (HK Systems 16in)"},
    {"asin": "B087CSV7NL", "title": "Scanner (Symcode 2D)"},
    {"asin": "B0BMB9T82D", "title": "Pax Stand (Hilipro Swivel Stand for Pax A35)"},
    {"asin": "B09GCR1VYL", "title": "Volcora Thermal Receipt Printer 80mm USB+Bluetooth"},
]

LOGIN_URL = (
    "https://www.amazon.com/ap/signin"
    "?openid.pape.max_auth_age=900"
    "&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F"
    "&openid.assoc_handle=usflex"
    "&openid.mode=checkid_setup"
    "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
)


async def dismiss_passkey_prompt(page) -> bool:
    """Try to dismiss the passkey popup and get to password field."""
    for sel in [
        "a:has-text('Sign in with a different')",
        "a:has-text('different sign-in method')",
        "a:has-text('Use password')",
        "a:has-text('Sign-in with your password')",
        "button:has-text('Use password')",
        "[data-testid='passkey-different-method-link']",
    ]:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                print(f"  [login] clicking passkey bypass: {sel[:60]}")
                await el.first.click()
                await page.wait_for_load_state("networkidle", timeout=10_000)
                return True
        except Exception:
            pass
    return False


async def login(page, email: str, password: str) -> None:
    print("→ Logging in...")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)

    # Email
    email_loc = page.locator("#ap_email_login").or_(page.locator("#ap_email"))
    await email_loc.first.wait_for(state="visible", timeout=20_000)
    await email_loc.first.fill(email)

    # Continue
    await page.locator("#continue input, #continue").first.click()
    await page.wait_for_load_state("networkidle", timeout=15_000)
    await page.wait_for_timeout(2_000)

    # Handle passkey prompt if password field not visible
    if not await page.locator("#ap_password").is_visible():
        print("  [login] passkey prompt — switching to password...")
        await dismiss_passkey_prompt(page)
        await page.wait_for_timeout(1_000)

    # Password
    pw_loc = page.locator("#ap_password")
    await pw_loc.wait_for(state="visible", timeout=20_000)
    await pw_loc.fill(password)

    # Submit via form.submit() to bypass passkey bubble overlay
    await page.evaluate("document.getElementById('signInSubmit').form.submit()")
    await page.wait_for_load_state("networkidle", timeout=20_000)
    await page.wait_for_timeout(3_000)

    current_url = page.url
    print(f"  [login] landed: {current_url[:80]}")

    if any(x in current_url for x in ("auth-mfa", "ap/cvf", "ap/challenge")):
        raise RuntimeError(
            "MFA / OTP required. Save session manually first:\n"
            "  python3 save_session.py"
        )

    print("  ✓ Login OK")


async def add_to_cart(page, asin: str, title: str) -> bool:
    """Navigate to product page and click Add to Cart."""
    url = f"https://www.amazon.com/dp/{asin}"
    print(f"\n→ {title}")
    print(f"   URL: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(2_000)

    # Screenshot for debugging
    await page.screenshot(path=f"/tmp/amazon_product_{asin}.png")

    # Try all Add-to-Cart selectors
    atc_selectors = [
        "#add-to-cart-button",
        "input[name='submit.add-to-cart']",
        "#submit.add-to-cart-ubb-announce",
        "input[id*='add-to-cart']",
        "button[id*='add-to-cart']",
        "[id^='add-to-cart']",
        "input[value*='Add to Cart']",
        "input[value*='Add to cart']",
    ]

    for sel in atc_selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click(timeout=8_000)
                await page.wait_for_timeout(2_500)
                print(f"   ✓ Clicked ATC via: {sel}")
                await page.screenshot(path=f"/tmp/amazon_after_atc_{asin}.png")
                return True
        except Exception:
            pass

    # JS fallback
    result = await page.evaluate("""() => {
        const btn = document.getElementById('add-to-cart-button') ||
                    document.querySelector('[name="submit.add-to-cart"]') ||
                    document.querySelector('[id*="add-to-cart"]') ||
                    document.querySelector('input[value*="Add to Cart"]');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    if result:
        await page.wait_for_timeout(2_500)
        print(f"   ✓ Added via JS fallback")
        await page.screenshot(path=f"/tmp/amazon_after_atc_{asin}.png")
        return True

    print(f"   ✗ No ATC button found — screenshot: /tmp/amazon_product_{asin}.png")
    return False


async def check_cart(page) -> list[str]:
    """Navigate to cart and return list of item titles found."""
    await page.goto(
        "https://www.amazon.com/gp/cart/view.html",
        wait_until="domcontentloaded",
        timeout=20_000,
    )
    await page.wait_for_timeout(2_000)
    await page.screenshot(path="/tmp/amazon_cart_final.png")

    # Try several selectors for cart item titles
    title_els = await page.query_selector_all(
        ".sc-product-title, "
        "[data-item-index] .a-truncate-full, "
        ".a-truncate-full.sc-product-title, "
        "span.a-truncate-full, "
        ".sc-list-item-content .a-truncate-full"
    )
    titles = []
    for el in title_els[:10]:
        try:
            t = (await el.inner_text()).strip()[:80]
            if t and len(t) > 5:
                titles.append(t)
        except Exception:
            pass

    if not titles:
        # Count items by ASIN attributes
        rows = await page.query_selector_all("[data-asin]")
        asins = set()
        for r in rows:
            a = await r.get_attribute("data-asin")
            if a:
                asins.add(a)
        titles = [f"[ASIN: {a}]" for a in asins]

    return titles


async def main():
    from playwright.async_api import async_playwright

    has_session = os.path.exists(SESSION_FILE)
    has_creds   = bool(EMAIL and PASSWORD)

    if not has_session and not has_creds:
        print("ERROR: No credentials found.")
        print("Set AMAZON_BUSINESS_EMAIL and AMAZON_PASSWORD, or run:")
        print("  python3 save_session.py")
        sys.exit(1)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=WebAuthentication,WebAuthenticationConditionalUI,"
                "PasswordManagerOnboarding,PasskeyAutofill",
            ],
        )

        ctx_kwargs = dict(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        if has_session:
            ctx_kwargs["storage_state"] = SESSION_FILE
            print(f"→ Resuming session from {SESSION_FILE}")

        ctx  = await browser.new_context(**ctx_kwargs)
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await ctx.new_page()

        try:
            # Login if no saved session
            if not has_session:
                await login(page, EMAIL, PASSWORD)
            else:
                # Quick check — are we still logged in?
                await page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(2_000)
                greeting = await page.locator("#nav-link-accountList-nav-line-1").inner_text()
                print(f"→ Session active: {greeting.strip()}")
                if "sign in" in greeting.lower():
                    print("  Session expired — logging in fresh...")
                    if not has_creds:
                        print("ERROR: Session expired and no credentials. Run save_session.py again.")
                        sys.exit(1)
                    await login(page, EMAIL, PASSWORD)

            # Add 4 items
            results = {}
            for item in ITEMS:
                ok = await add_to_cart(page, item["asin"], item["title"])
                results[item["title"]] = ok

            # Check cart
            print("\n→ Verifying cart...")
            cart_titles = await check_cart(page)

            # Report
            print("\n" + "=" * 60)
            print("RESULT SUMMARY")
            print("=" * 60)
            for title, ok in results.items():
                status = "✓ Added" if ok else "✗ FAILED"
                print(f"  {status}  {title}")

            print(f"\nCart items found: {len(cart_titles)}")
            for t in cart_titles:
                print(f"  • {t}")

            print("\nScreenshots:")
            for item in ITEMS:
                print(f"  /tmp/amazon_product_{item['asin']}.png")
                print(f"  /tmp/amazon_after_atc_{item['asin']}.png")
            print("  /tmp/amazon_cart_final.png")

            # Save updated session
            await ctx.storage_state(path=SESSION_FILE)
            print(f"\n→ Session saved to {SESSION_FILE}")

        finally:
            await browser.close()


asyncio.run(main())
