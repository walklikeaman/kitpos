"""
Standalone login test.
Checks ONLY that we can sign in to Amazon Business and reach the home page.
"""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

EMAIL    = os.getenv("AMAZON_BUSINESS_EMAIL", "")
PASSWORD = os.getenv("AMAZON_PASSWORD", "")

LOGIN_URL = (
    "https://www.amazon.com/ap/signin"
    "?openid.pape.max_auth_age=900"
    "&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F"
    "&openid.assoc_handle=usflex"
    "&openid.mode=checkid_setup"
    "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
)

# Also try if the above fails
SIMPLE_LOGIN_URL = "https://www.amazon.com/gp/sign-in.html"

async def test_login():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=WebAuthentication,PasswordManagerOnboarding,PasskeyAutofill",
                "--disable-webauthn-ui",
            ],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = await ctx.new_page()

        # 1. Go to login page — use simple URL to avoid ax/claim redirect
        print("1. Opening login page...")
        await page.goto(SIMPLE_LOGIN_URL, wait_until="networkidle", timeout=30_000)
        print(f"   URL: {page.url[:80]}")

        # 2. Enter email
        print("2. Entering email...")
        email_field = page.locator("#ap_email_login").or_(page.locator("#ap_email"))
        await email_field.first.wait_for(state="visible", timeout=15_000)
        await email_field.first.fill(EMAIL)
        print(f"   Filled: {EMAIL}")

        # 3. Click Continue
        print("3. Clicking Continue...")
        await page.locator("#continue input, #continue").first.click()
        await page.wait_for_load_state("networkidle", timeout=15_000)
        print(f"   URL after Continue: {page.url[:80]}")

        # 4. Wait for passkey popup and screenshot it
        await page.wait_for_timeout(2_500)
        await page.screenshot(path="/tmp/amazon_after_continue.png")
        print("   Screenshot after Continue: /tmp/amazon_after_continue.png")

        pw_visible = await page.locator("#ap_password").is_visible()
        print(f"   Password field visible: {pw_visible}")

        # Dump ALL visible elements to find the popup close button
        print("   All visible elements:")
        for sel in ["button", "input[type='submit']", "input[type='button']", "[role='dialog']", "[role='alertdialog']", ".a-modal", "[class*='modal']", "[class*='dialog']", "[class*='passkey']", "[aria-label*='close' i]", "[id*='passkey']"]:
            els = await page.query_selector_all(sel)
            for el in els[:5]:
                try:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip()[:80]
                        cls = await el.get_attribute("class") or ""
                        idd = await el.get_attribute("id") or ""
                        aria = await el.get_attribute("aria-label") or ""
                        print(f"     [{sel}] id='{idd}' class='{cls[:40]}' aria='{aria}' text='{text}'")
                except Exception:
                    pass

        if not pw_visible:
            print("4. Passkey prompt detected — looking for 'use different method' link...")
            found = False
            for sel in [
                "a:has-text('Sign in with a different')",
                "a:has-text('different sign-in method')",
                "a:has-text('Use password')",
                "a:has-text('Sign-in with your password')",
                "button:has-text('Use password')",
                "[data-testid='passkey-different-method-link']",
            ]:
                el = page.locator(sel)
                try:
                    if await el.count() > 0 and await el.first.is_visible():
                        print(f"   Clicking: {sel[:60]}")
                        await el.first.click()
                        await page.wait_for_load_state("networkidle", timeout=10_000)
                        found = True
                        break
                except Exception as e:
                    print(f"   Skip {sel[:40]}: {e}")

            if not found:
                # Dump page content for debugging
                print("   Could not find bypass link. Page text snippet:")
                try:
                    body = await page.locator("body").inner_text()
                    print("   " + body[:500].replace("\n", " "))
                except Exception:
                    pass
                await page.screenshot(path="/tmp/amazon_passkey_debug.png")
                print("   Screenshot saved: /tmp/amazon_passkey_debug.png")
                await browser.close()
                return

        # 5. Fill password
        print("5. Filling password...")
        await page.locator("#ap_password").wait_for(state="visible", timeout=15_000)
        await page.locator("#ap_password").fill(PASSWORD)

        # Screenshot before submit
        await page.screenshot(path="/tmp/amazon_before_submit.png")
        print("   Screenshot before submit: /tmp/amazon_before_submit.png")

        # 6. Submit — try pressing Enter on the password field (bypasses any overlay)
        print("6. Submitting via Enter key on password field...")
        await page.locator("#ap_password").press("Enter")
        await page.wait_for_load_state("networkidle", timeout=15_000)
        await page.wait_for_timeout(2_000)

        # If that didn't work, try JS form submit
        if "ax/claim" in page.url and "sign" in (await page.locator("body").inner_text()).lower()[:50]:
            print("   Enter didn't work — trying JS form submit...")
            await page.evaluate("document.getElementById('signInSubmit').form.submit()")
            await page.wait_for_load_state("networkidle", timeout=15_000)

        await page.wait_for_timeout(3_000)
        final_url = page.url
        print(f"7. Final URL: {final_url[:120]}")

        # Screenshot of current state (right after sign-in, BEFORE navigating)
        await page.screenshot(path="/tmp/amazon_after_signin.png")
        print("   Screenshot: /tmp/amazon_after_signin.png")

        # Dump visible text
        try:
            body_text = await page.locator("body").inner_text()
            print(f"   Page text (first 600 chars):\n{body_text[:600]}")
        except Exception:
            pass

        # List all visible buttons and links
        print("   Visible buttons/links:")
        for sel in ["button", "input[type='submit']", "a"]:
            els = await page.query_selector_all(sel)
            for el in els[:8]:
                try:
                    visible = await el.is_visible()
                    if visible:
                        text = (await el.inner_text()).strip()[:60]
                        href = await el.get_attribute("href") or ""
                        val = await el.get_attribute("value") or ""
                        print(f"     [{sel}] text='{text}' val='{val}' href='{href[:40]}'")
                except Exception:
                    pass

        await browser.close()

asyncio.run(test_login())
