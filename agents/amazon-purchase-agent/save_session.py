"""
Manual login helper — opens a real browser window where you can log in manually,
then saves the session cookies for automated use.

Usage:
  python3 save_session.py

After the browser opens:
  1. Log in to amazon.com manually
  2. Make sure you see your name in the top-right nav (e.g. "Hello, Nikita")
  3. Press Enter in this terminal
  4. Session is saved to amazon_session.json
"""
import asyncio
from playwright.async_api import async_playwright

SESSION_FILE = "amazon_session.json"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        page = await ctx.new_page()
        await page.goto("https://www.amazon.com/ap/signin?openid.assoc_handle=usflex"
                        "&openid.mode=checkid_setup"
                        "&openid.ns=http://specs.openid.net/auth/2.0")

        print("=" * 60)
        print("Browser is open. Log in to Amazon manually.")
        print("When you see your name in the top-right, press Enter here.")
        print("=" * 60)

        try:
            input("Press Enter after logging in... ")
        except EOFError:
            pass

        # Save session state (cookies + localStorage)
        await ctx.storage_state(path=SESSION_FILE)
        print(f"✅ Session saved to {SESSION_FILE}")
        print("   You can now run the agent — it will use this session.")

        await browser.close()

asyncio.run(main())
