"""
Amazon Business browser session via Playwright.

Handles login, reorder search, add-to-cart, address management,
delivery date extraction, and order placement.
"""
from __future__ import annotations
import asyncio
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Locator

from config import config


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BrowserCartItem:
    asin: str
    title: str
    price: float
    seller: str
    estimated_delivery: date | None
    qty: int


@dataclass
class BrowserOrderResult:
    order_id: str
    total: str
    delivery_info: str


# ---------------------------------------------------------------------------
# Delivery date parser
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_delivery_date(text: str) -> date | None:
    """Extract the earliest date from delivery strings like 'Apr 24 - Apr 27'."""
    text = text.lower().strip()
    # Match patterns: "apr 24", "april 24", "april 24 - april 27"
    match = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})', text)
    if match:
        month = _MONTH_MAP[match.group(1)[:3]]
        day = int(match.group(2))
        year = date.today().year
        candidate = date(year, month, day)
        # If date is in the past, it's next year
        if candidate < date.today():
            candidate = date(year + 1, month, day)
        return candidate
    return None


# ---------------------------------------------------------------------------
# Amazon session
# ---------------------------------------------------------------------------

class AmazonSession:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._timeout = 10_000  # ms

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> None:
        """Sign in to Amazon Business using the exact URL from recorded flow."""
        p = self._page

        # Direct signin URL — return_to is plain amazon.com homepage, avoids ax/claim redirect
        await p.goto(
            "https://www.amazon.com/ap/signin"
            "?openid.pape.max_auth_age=900"
            "&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F"
            "&openid.assoc_handle=usflex"
            "&openid.mode=checkid_setup"
            "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0",
            wait_until="networkidle",
            timeout=30_000,
        )

        # Email — try multiple known selectors
        email_locator = p.locator("#ap_email_login").or_(p.locator("#ap_email"))
        await email_locator.first.wait_for(state="visible", timeout=20_000)
        await email_locator.first.click()
        await email_locator.first.fill(email)

        # Continue button (from Amazon1.js: '#continue input')
        await p.locator("#continue input, #continue").first.click()
        await p.wait_for_load_state("networkidle", timeout=15_000)

        # After Continue, Amazon may show a passkey challenge page.
        # We wait for EITHER the password field OR a "use different method" link.
        # NEVER press Escape — that closes the whole login form.
        await p.wait_for_timeout(2_000)

        if not await p.locator("#ap_password").is_visible():
            print("  [login] passkey prompt detected — switching to password...")

            # These links navigate WITHIN the login flow to the password page.
            # Priority order based on what Amazon renders.
            passkey_bypass_links = [
                "a:has-text('Sign in with a different')",          # most common
                "a:has-text('different sign-in method')",
                "a:has-text('Use password')",
                "a:has-text('Sign-in with your password')",
                "a:has-text('Use a different')",
                "[id*='passkey-different'], [id*='different-method']",
                "[data-testid='passkey-different-method-link']",
                "#ap-account-fixup-phone-number-unrequire-link",
                # Sometimes it's a button
                "button:has-text('Use password')",
                "button:has-text('different')",
            ]

            switched = False
            for sel in passkey_bypass_links:
                try:
                    el = p.locator(sel)
                    if await el.count() > 0 and await el.first.is_visible():
                        print(f"  [login] clicking: {sel[:50]}")
                        await el.first.click()
                        # Wait for navigation to password page
                        await p.wait_for_load_state("networkidle", timeout=10_000)
                        switched = True
                        break
                except Exception:
                    continue

            if not switched:
                # Passkey prompt might be a modal overlay — click its close X (not Escape)
                for close_sel in [
                    ".a-modal-scroller .a-icon-close",
                    "[aria-label='Close']",
                    ".a-popover-close",
                    "button[aria-label*='close' i]",
                    "button[aria-label*='Close' i]",
                ]:
                    try:
                        btn = p.locator(close_sel)
                        if await btn.count() > 0 and await btn.first.is_visible():
                            print(f"  [login] closing overlay via: {close_sel}")
                            await btn.first.click()
                            await p.wait_for_timeout(800)
                            break
                    except Exception:
                        continue

        # Password field must now be visible
        await p.locator("#ap_password").wait_for(state="visible", timeout=20_000)
        await p.locator("#ap_password").fill(password)

        # Submit password form via JS — bypasses any passkey bubble overlay
        # (clicking #signInSubmit can be blocked by Chrome's passkey UI)
        await p.evaluate("document.getElementById('signInSubmit').form.submit()")
        await p.wait_for_load_state("networkidle", timeout=15_000)

        # Wait briefly for redirect to settle
        await p.wait_for_timeout(3_000)
        current_url = p.url
        print(f"  [login] landed on: {current_url[:80]}")

        # MFA / CAPTCHA / OTP check
        if any(x in current_url for x in ("auth-mfa", "ap/cvf", "ap/challenge", "ap/apa")):
            raise RuntimeError(
                "MFA or CAPTCHA required. Complete it manually in the browser, "
                "then press Enter here to continue."
            )

        # If still on signin page, something went wrong
        if "ap/signin" in current_url or "ap/password" in current_url:
            raise RuntimeError(f"Login failed — still on signin page: {current_url}")

        # Amazon Business ax/claim page — account linking flow
        # This appears when Business account needs to accept terms or link to personal account.
        # We need to click through it to actually land on the authenticated homepage.
        if "ax/claim" in current_url:
            print("  [login] Amazon Business claim page detected — clicking through...")
            for sel in [
                "input[type='submit']",
                "button[type='submit']",
                "a:has-text('Continue')",
                "span:has-text('Continue') >> ..",
                "input[value*='Continue' i]",
                "input[value*='Sign in' i]",
                "[data-testid='claim-continue-button']",
            ]:
                try:
                    btn = p.locator(sel)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        print(f"  [login] clicking: {sel[:50]}")
                        await btn.first.click()
                        await p.wait_for_load_state("networkidle", timeout=10_000)
                        await p.wait_for_timeout(2_000)
                        break
                except Exception:
                    continue
            print(f"  [login] after claim: {p.url[:80]}")

        # Verify authentication — check we are NOT on a login/claim page
        await p.wait_for_timeout(1_500)
        final_url = p.url

        # If we landed on amazon.com (not signin), we're good
        if "amazon.com" in final_url and not any(x in final_url for x in ("ap/signin", "ap/password", "ax/claim")):
            # Try to read the greeting — Business accounts may use different nav IDs
            nav_text = ""
            for nav_sel in [
                "#nav-link-accountList-nav-line-1",
                "#nav-link-accountList span.nav-line-1",
                "a#nav-link-accountList span",
                "#nav-tools a.nav-a[href*='account']",
            ]:
                el = await p.query_selector(nav_sel)
                if el:
                    t = (await el.inner_text()).strip()
                    if t and "sign in" not in t.lower():
                        nav_text = t
                        break
            print(f"  ✓ Login successful — {nav_text or 'authenticated (nav not parsed)'}")
        else:
            raise RuntimeError(
                f"Login did not complete — landed on: {final_url[:80]}"
            )

    async def set_delivery_zip(self, zip_code: str) -> None:
        """
        Set the delivery ZIP in Amazon's nav bar so product delivery estimates
        reflect the correct location. Without this, Amazon shows default long estimates.
        """
        p = self._page
        await p.goto("https://www.amazon.com", wait_until="domcontentloaded")

        # Click the "Deliver to" button in the nav
        deliver_btn = p.locator("#nav-global-location-popover-link, #glow-ingress-block")
        if await deliver_btn.count() == 0:
            return

        # Only click if visible — element exists but may be hidden on Business accounts
        try:
            await deliver_btn.first.click(timeout=5_000)
        except Exception:
            print(f"  [location] delivery location button not clickable — skipping (ZIP may already be set)")
            return
        await p.wait_for_timeout(800)

        # Fill ZIP code in the location modal
        zip_input = p.locator(
            "#GLUXZipUpdateInput, "
            "input[placeholder*='ZIP'], "
            "input[data-component-type*='zip'], "
            "#GLUXZipUpdate input"
        )
        if await zip_input.count() > 0:
            await zip_input.first.click(click_count=3)
            await zip_input.first.fill(zip_code)

            # Apply
            apply_btn = p.locator(
                "#GLUXZipUpdate input[type='submit'], "
                "input[aria-labelledby*='GLUXZipUpdate'], "
                ":text('Apply'), :text('Done')"
            )
            if await apply_btn.count() > 0:
                await apply_btn.first.click()
                await p.wait_for_timeout(1_000)
                print(f"  [location] delivery ZIP set to {zip_code}")

        # Close modal if still open — ignore if already gone
        try:
            close = p.locator(".a-popover-footer .a-button-primary, #GLUXConfirmClose")
            if await close.count() > 0 and await close.first.is_visible():
                await close.first.click(timeout=3_000)
                await p.wait_for_timeout(500)
        except Exception:
            pass

    async def resume_after_mfa(self) -> None:
        """Call after user completes MFA manually."""
        await self._page.wait_for_selector("#nav-link-accountList", timeout=60_000)

    # ------------------------------------------------------------------
    # Order history (actual past orders — most reliable source)
    # ------------------------------------------------------------------

    async def get_order_history(self, max_pages: int = 3) -> list[dict]:
        """
        Scrape Amazon Business order history pages.
        Returns list of {asin, title, price, order_id, order_date} dicts.
        Covers the last `max_pages` pages of order history.
        """
        p = self._page
        all_orders: list[dict] = []
        seen_asins: set[str] = set()

        for page_num in range(max_pages):
            url = (
                "https://www.amazon.com/gp/your-account/order-history"
                f"?opt=ab&digitalOrders=0&unifiedOrders=1&returnTo=&orderFilter=year-2025&startIndex={page_num * 10}"
            )
            try:
                await p.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                break

            # Each order block
            order_cards = await p.query_selector_all(".order-card, [data-testid='order-card'], .a-box-group.order")
            if not order_cards:
                # Try alternate selector used by newer order history layout
                order_cards = await p.query_selector_all(".order, [class*='order-row']")

            order_id = ""
            order_date = ""

            for card in order_cards:
                # Extract order metadata
                id_el = await card.query_selector(".yohtmlc-order-id span:last-child, [class*='order-id'] span")
                if id_el:
                    order_id = (await id_el.inner_text()).strip()
                date_el = await card.query_selector(".order-date-invoice-item span:last-child, .a-color-secondary.a-size-small")
                if date_el:
                    order_date = (await date_el.inner_text()).strip()

                # Product links contain ASIN in /dp/ASIN pattern
                product_links = await card.query_selector_all("a[href*='/dp/']")
                for link in product_links:
                    href = await link.get_attribute("href") or ""
                    asin_m = re.search(r"/dp/([A-Z0-9]{10})", href)
                    if not asin_m:
                        continue
                    asin = asin_m.group(1)
                    if asin in seen_asins:
                        continue
                    seen_asins.add(asin)

                    title_el = await link.query_selector("span") or link
                    title = (await title_el.inner_text()).strip()
                    if not title:
                        title = await link.get_attribute("title") or ""

                    price_el = await card.query_selector(".a-price .a-offscreen, .item-price .a-offscreen")
                    price_raw = (await price_el.inner_text()).strip() if price_el else "0"
                    try:
                        price = float(re.sub(r"[^\d.]", "", price_raw))
                    except ValueError:
                        price = 0.0

                    all_orders.append({
                        "asin": asin,
                        "title": title,
                        "price": price,
                        "order_id": order_id,
                        "order_date": order_date,
                        "seller": "Amazon",
                        "score": 0.0,
                    })

            if not order_cards:
                break

        return all_orders

    async def search_order_history(self, query: str) -> list[dict]:
        """Search past orders for a matching item. Returns scored results."""
        history = await self.get_order_history()
        if not history:
            return []

        import re as _re
        def tokenize(s: str) -> set[str]:
            return set(_re.sub(r"[^\w\s]", " ", s.lower()).split())

        q_tokens = tokenize(query)
        for item in history:
            t_tokens = tokenize(item["title"])
            item["score"] = len(q_tokens & t_tokens) / max(len(q_tokens), 1)

        history = [r for r in history if r["score"] > 0]
        history.sort(key=lambda x: x["score"], reverse=True)
        return history

    # ------------------------------------------------------------------
    # Reorder list search
    # ------------------------------------------------------------------

    async def search_reorder(self, query: str) -> list[dict]:
        """
        Search the Reorder List for a product by keyword.
        Returns list of {asin, title, price, seller} dicts.
        """
        p = self._page
        try:
            await p.goto(
                "https://www.amazon.com/gp/buy/reorder/handlers/display.html",
                wait_until="domcontentloaded", timeout=45_000,
            )
        except Exception:
            return []  # Reorder page unavailable — fall through to regular search

        results = []
        # Each reorder item has id pattern: item_ASIN-<ASIN>-ATVPDKIKX0DER
        items = await p.query_selector_all("[id^='item_ASIN-']")
        for item_el in items:
            item_id = await item_el.get_attribute("id") or ""
            asin_match = re.search(r"item_ASIN-([A-Z0-9]+)-", item_id)
            if not asin_match:
                continue
            asin = asin_match.group(1)

            title_el = await item_el.query_selector("span.g-title")
            title = (await title_el.inner_text()).strip() if title_el else ""

            price_el = await item_el.query_selector("span.a-price .a-offscreen")
            price_raw = (await price_el.inner_text()).strip() if price_el else "0"
            try:
                price = float(re.sub(r"[^\d.]", "", price_raw))
            except ValueError:
                price = 0.0

            # Simple relevance: keyword overlap
            q_tokens = set(query.lower().split())
            t_tokens = set(title.lower().split())
            score = len(q_tokens & t_tokens) / max(len(q_tokens), 1)

            results.append({"asin": asin, "title": title, "price": price, "seller": "Amazon", "score": score})

        results.sort(key=lambda x: x["score"], reverse=True)
        return [r for r in results if r["score"] > 0]

    # ------------------------------------------------------------------
    # Regular search
    # ------------------------------------------------------------------

    async def search_regular(self, query: str, max_results: int = 5) -> list[dict]:
        """Search Amazon Business catalog and return top N results with delivery dates from search page."""
        p = self._page
        await p.goto(
            f"https://www.amazon.com/s?k={query.replace(' ', '+')}&i=amazon-business",
            wait_until="domcontentloaded",
            timeout=45_000,
        )

        import re as _re

        def tokenize(s):
            return set(_re.sub(r"[^\w\s]", " ", s.lower()).split())

        results = []
        cards = await p.query_selector_all("[data-component-type='s-search-result']")
        for card in cards[:max_results]:
            asin = await card.get_attribute("data-asin") or ""
            title_el = await card.query_selector("h2 span")
            title = (await title_el.inner_text()).strip() if title_el else ""
            price_el = await card.query_selector("span.a-price .a-offscreen")
            price_raw = (await price_el.inner_text()).strip() if price_el else "0"
            try:
                price = float(_re.sub(r"[^\d.]", "", price_raw))
            except ValueError:
                price = 0.0

            # Seller — look specifically for "sold by" text, avoid picking up delivery dates
            seller = "Unknown"
            for s_sel in [
                "span:has-text('Sold by')",
                ".s-sold-by-section span",
                "[aria-label*='sold by']",
                "span.a-size-small:has-text('Visit')",
            ]:
                s_el = await card.query_selector(s_sel)
                if s_el:
                    raw = (await s_el.inner_text()).strip()
                    # Strip "Sold by" prefix and clean up
                    raw = re.sub(r"(?i)sold by\s*", "", raw).strip()
                    if raw and not re.search(r"\d{4}-\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", raw.lower()):
                        seller = raw
                        break

            # Try to get delivery date from search card
            delivery_date: date | None = None
            for d_sel in [
                "[data-cy='delivery-recipe'] span",
                ".s-delivery-date",
                "span[aria-label*='delivery']",
                "[class*='delivery'] span",
            ]:
                d_el = await card.query_selector(d_sel)
                if d_el:
                    d_text = await d_el.inner_text()
                    delivery_date = _parse_delivery_date(d_text)
                    if delivery_date:
                        break

            q_tokens = tokenize(query)
            t_tokens = tokenize(title)
            score = len(q_tokens & t_tokens) / max(len(q_tokens), 1)

            if asin:
                results.append({
                    "asin": asin, "title": title, "price": price,
                    "seller": seller, "score": score,
                    "delivery_date_from_search": delivery_date,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Product page — delivery date + seller check
    # ------------------------------------------------------------------

    async def get_product_details(self, asin: str, prefetched: dict | None = None) -> dict:
        """
        Get delivery date, seller, price for an ASIN.
        Uses prefetched data from search card when available (avoids extra page load).
        Falls back to product page visit if delivery date not available.
        """
        # If we already have delivery date from search, use it
        if prefetched and prefetched.get("delivery_date_from_search"):
            return {
                "delivery_date": prefetched["delivery_date_from_search"],
                "seller": prefetched.get("seller", "Unknown"),
                "price": prefetched.get("price", 0.0),
                "has_subscription": False,
            }

        p = self._page
        try:
            await p.goto(f"https://www.amazon.com/dp/{asin}", wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            print(f"  [warn] product page timeout for {asin}: {e}")
            return {"delivery_date": None, "seller": "Unknown", "price": 0.0, "has_subscription": False}

        # Delivery date
        delivery_date: date | None = None
        delivery_el = await p.query_selector("#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE")
        if not delivery_el:
            delivery_el = await p.query_selector("[data-csa-c-delivery-price]")
        if delivery_el:
            delivery_text = await delivery_el.inner_text()
            delivery_date = _parse_delivery_date(delivery_text)

        # Seller
        seller = "Unknown"
        seller_el = await p.query_selector("#sellerProfileTriggerId, #merchant-info a")
        if seller_el:
            seller = (await seller_el.inner_text()).strip()

        # Price
        price = 0.0
        price_el = await p.query_selector("#corePrice_feature_div .a-offscreen, #price_inside_buybox")
        if price_el:
            try:
                price = float(re.sub(r"[^\d.]", "", await price_el.inner_text()))
            except ValueError:
                pass

        # Subscription check
        has_subscription = await p.query_selector("#snsAccordionRowMiddle, #sns-base-widget") is not None

        return {
            "delivery_date": delivery_date,
            "seller": seller,
            "price": price,
            "has_subscription": has_subscription,
        }

    # ------------------------------------------------------------------
    # Add to cart from Reorder List
    # ------------------------------------------------------------------

    async def add_from_reorder(self, asin: str, qty: int) -> bool:
        """
        Add item from Reorder List with specified quantity.
        Returns True on success.
        """
        p = self._page
        qty_id = f"WLNOTES_requestedQuantity_ASIN-{asin}-ATVPDKIKX0DER"
        add_btn_selector = f"#pab-ASIN-{asin}-ATVPDKIKX0DER span a, #item_ASIN-{asin}-ATVPDKIKX0DER .pab-action a"

        try:
            qty_input = p.locator(f"#{qty_id}")
            await qty_input.wait_for(timeout=5_000)
            await qty_input.fill(str(qty))
            await p.locator(add_btn_selector).first.click()
            # Wait for cart count to update
            await p.wait_for_timeout(1_500)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Add to cart from product page
    # ------------------------------------------------------------------

    async def add_to_cart(self, asin: str, qty: int) -> bool:
        """Navigate to product page and add to cart."""
        p = self._page
        await p.goto(f"https://www.amazon.com/dp/{asin}", wait_until="domcontentloaded")

        # Set quantity if dropdown exists and is visible
        if qty > 1:
            qty_sel = await p.query_selector("#quantity")
            if qty_sel:
                try:
                    visible = await qty_sel.is_visible()
                    if visible:
                        await qty_sel.select_option(str(qty) if qty <= 30 else "30", timeout=3_000)
                except Exception:
                    pass  # quantity will be adjustable in cart if needed

        btn = p.locator("#add-to-cart-button, #submit.add-to-cart-ubb-announce")
        try:
            await btn.first.click(timeout=5_000)
            await p.wait_for_timeout(1_500)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Checkout flow
    # ------------------------------------------------------------------

    async def _dismiss_overlays(self) -> None:
        """Close any overlay modals (warranty, protection plan, etc.) blocking interaction."""
        p = self._page
        for sel in [
            # "No thanks" / "Decline" on warranty modal
            ".attach-dss-modal-layer button:has-text('No thanks')",
            ".attach-dss-modal-layer button:has-text('No Thank')",
            ".attach-dss-modal-layer [data-action*='close']",
            ".attach-dss-modal-layer .a-button-close",
            # Generic close / dismiss
            "[id*='attach-close'], [id*='dss-modal'] .a-icon-close",
            "button:has-text('No thanks')",
            "button:has-text('Decline')",
        ]:
            try:
                btn = p.locator(sel)
                if await btn.count() > 0 and await btn.first.is_visible():
                    print(f"  [overlay] dismissing: {sel.split(':')[0]}")
                    await btn.first.click(timeout=3_000)
                    await p.wait_for_timeout(600)
            except Exception:
                pass

        # If still blocked, try pressing Escape
        overlay = p.locator(".attach-dss-modal-layer, [class*='attach-modal']")
        if await overlay.count() > 0 and await overlay.first.is_visible():
            await p.keyboard.press("Escape")
            await p.wait_for_timeout(500)

    async def go_to_cart(self) -> None:
        await self._dismiss_overlays()
        # Navigate directly with retry — ERR_ABORTED can happen if prev nav is still in flight
        for attempt in range(3):
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=5_000)
            except Exception:
                pass
            try:
                await self._page.goto(
                    "https://www.amazon.com/gp/cart/view.html",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                return
            except Exception as e:
                if attempt < 2:
                    await self._page.wait_for_timeout(1_500)
                    continue
                raise

    async def proceed_to_checkout(self) -> None:
        p = self._page

        # Try all known checkout button selectors
        for sel in [
            "#desktop-ptc-button-celWidget input",
            "#sc-buy-box-ptc-button input",
            "[name='proceedToRetailCheckout']",
            "input[title*='checkout' i]",
            "input[value*='Checkout' i]",
            "a:has-text('Proceed to checkout')",
            "span:has-text('Proceed to checkout')",
        ]:
            try:
                btn = p.locator(sel)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click(timeout=8_000)
                    await p.wait_for_load_state("domcontentloaded")
                    break
            except Exception:
                continue
        else:
            # Fallback: navigate directly to checkout
            await p.goto("https://www.amazon.com/gp/buy/buy-redirect/handlers/display.html?action=purchaseInitiator", wait_until="domcontentloaded", timeout=30_000)

        await p.wait_for_timeout(1_000)

        # Business checkout page may have an extra "Buy now" / "Place order" step
        for byg_sel in [
            "#checkout-byg-ptc-button a",
            ".checkout-byg-ptc-button a",
            "a:has-text('Place your order')",
            "[data-testid='checkout-byg-ptc-button']",
        ]:
            try:
                byg_btn = p.locator(byg_sel)
                if await byg_btn.count() > 0 and await byg_btn.first.is_visible():
                    await byg_btn.first.click(timeout=8_000)
                    await p.wait_for_load_state("domcontentloaded")
                    break
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Address management
    # ------------------------------------------------------------------

    # State abbreviation → full name map (for dropdown filter)
    _STATE_NAMES = {
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

    async def select_or_create_address(
        self,
        full_name: str,
        street: str,
        city: str,
        state: str,
        zip_code: str,
        phone: str = "",
    ) -> None:
        """
        Check if address already exists on checkout page, use it;
        otherwise create a new one via the modal form.
        Follows the exact flow from Amazon1.js recording.
        """
        p = self._page

        # --- Try to use existing address ---
        # Strategy: find any element on the page containing our ZIP,
        # click it (select it), then click Continue / Use this address.
        print(f"  [address] checking for existing address with ZIP {zip_code}...")

        # Wider selector set to catch all Amazon checkout address row formats
        addr_rows = await p.query_selector_all(
            "[data-testid*='address-row'], "
            "[id*='address-book-entry'], "
            ".address-book-entry, "
            "[class*='address-row'], "
            "span[class*='address-radio']"
        )
        existing_found = False
        for row in addr_rows:
            try:
                text = (await row.inner_text()).lower()
                if zip_code in text:
                    print(f"  [address] found existing address → selecting it")
                    await row.click()
                    await p.wait_for_timeout(800)
                    existing_found = True
                    break
            except Exception:
                continue

        if existing_found:
            # Click "Use this address" / "Ship to this address" / "Deliver here"
            for use_sel in [
                "[data-testid='bottom-continue-button']",
                "input[name='enterAddressReturnAction']",
                "a:has-text('Ship to this address')",
                "a:has-text('Deliver to this address')",
                "input[value*='Use this address' i]",
                "span:has-text('Use this address')",
            ]:
                try:
                    btn = p.locator(use_sel)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click(timeout=self._timeout)
                        await p.wait_for_load_state("domcontentloaded")
                        return
                except Exception:
                    continue
            return  # address was selected, continue even if button not found

        # --- Add new address ---
        add_link = p.locator(
            "#add-new-address-popover-link, "
            ":text('Add a new delivery address'), "
            ":text('Add a new address')"
        )
        await add_link.first.click(timeout=self._timeout)
        # Wait for modal to fully open
        await p.wait_for_selector("#address-ui-widgets-enterAddressFullName", timeout=10_000)

        # Fill full name
        name_field = p.locator("#address-ui-widgets-enterAddressFullName")
        await name_field.click(click_count=3)
        await name_field.fill(full_name)

        # Fill phone
        if phone:
            phone_field = p.locator("#address-ui-widgets-enterAddressPhoneNumber")
            await phone_field.click(click_count=3)
            await phone_field.fill(phone)

        # Fill street
        street_field = p.locator("#address-ui-widgets-enterAddressLine1")
        await street_field.click(click_count=3)
        await street_field.fill(street)

        # Fill city
        city_field = p.locator("#address-ui-widgets-enterAddressCity")
        await city_field.click(click_count=3)
        await city_field.fill(city)

        # State dropdown — type abbreviation to filter, then click full-name option
        # Matches exactly what Amazon1.js does: type "ok" → click "Oklahoma"
        state_abbr = state.upper()[:2]
        state_full = self._STATE_NAMES.get(state_abbr, state)
        state_trigger = p.locator("#address-ui-widgets-enterAddressStateOrRegion > span > span")
        if await state_trigger.count() > 0:
            await state_trigger.first.click()
            await p.wait_for_timeout(300)
            await p.keyboard.type(state_abbr.lower())
            await p.wait_for_timeout(300)
            # Click the option that matches full state name inside the dropdown
            state_option = p.locator(
                f"#address-ui-widgets-enterAddressStateOrRegion-dropdown-nativeId li:has-text('{state_full}'), "
                f"li:has-text('{state_full}')"
            )
            if await state_option.count() > 0:
                await state_option.first.click()
            else:
                # Fallback: select by value on native <select>
                native = p.locator(f"select[id*='StateOrRegion']")
                if await native.count() > 0:
                    await native.select_option(label=state_full)

        # Fill ZIP
        zip_field = p.locator("#address-ui-widgets-enterAddressPostalCode")
        await zip_field.click(click_count=3)
        await zip_field.fill(zip_code)

        await p.wait_for_timeout(400)

        # Submit — "Use this address" button inside the modal
        submit = p.locator(
            "[data-testid='bottom-continue-button'], "
            "#address-ui-widgets-form-submit-button input, "
            "#address-ui-widgets-form-submit-button"
        )
        await submit.first.click(timeout=self._timeout)
        await p.wait_for_load_state("domcontentloaded")

        # Handle Amazon address suggestion dialog
        await self._handle_address_suggestion(zip_code)

    async def _handle_address_suggestion(self, expected_zip: str) -> None:
        """Accept Amazon's address suggestion if it preserves the ZIP code."""
        p = self._page
        await p.wait_for_timeout(600)

        suggestion_btn = p.locator("[data-testid='bottom-continue-button'], :text('Use suggested address')")
        if await suggestion_btn.count() > 0:
            # Read suggested address
            suggested_text = ""
            suggested_el = await p.query_selector(".a-box.suggested-address, [data-component='suggested-address']")
            if suggested_el:
                suggested_text = await suggested_el.inner_text()

            if expected_zip in suggested_text or not suggested_text:
                await suggestion_btn.first.click()
                await p.wait_for_load_state("domcontentloaded")
            else:
                # Keep original
                keep_btn = p.locator(":text('Use entered address'), :text('Keep entered address')")
                if await keep_btn.count() > 0:
                    await keep_btn.first.click()
                    await p.wait_for_load_state("domcontentloaded")

    # ------------------------------------------------------------------
    # Delivery option + place order
    # ------------------------------------------------------------------

    async def select_fastest_free_delivery(self) -> None:
        """Select first available free/Prime delivery option."""
        p = self._page
        free_options = p.locator(
            "[id*='FREE'], [id*='Prime'], "
            "input[type='radio'][id*='delivery']"
        )
        if await free_options.count() > 0:
            await free_options.first.click()

    async def place_order(self) -> BrowserOrderResult:
        """Click Place Order and extract order confirmation."""
        p = self._page

        # Take screenshot for debugging before attempting to place order
        await p.screenshot(path="/tmp/amazon_before_place_order.png")
        print("  Screenshot: /tmp/amazon_before_place_order.png")

        # Dump page for selector discovery
        print("  Scanning for Place Order button...")
        for sel in [
            "[data-testid='SPC_selectPlaceOrder']",
            "#submitOrderButtonId input",
            "[name='placeYourOrder1']",
            "input[value*='Place']",
            "input[aria-labelledby*='place']",
            "span:has-text('Place your order')",
            "button:has-text('Place your order')",
            "[id*='placeOrder']",
            "[id*='place-order']",
            "[class*='place-order']",
            "input[type='submit']",
        ]:
            els = await p.query_selector_all(sel)
            for el in els[:3]:
                try:
                    if await el.is_visible():
                        text = (await el.inner_text() if hasattr(el, 'inner_text') else "").strip()[:60]
                        val = await el.get_attribute("value") or ""
                        idd = await el.get_attribute("id") or ""
                        name = await el.get_attribute("name") or ""
                        print(f"    FOUND [{sel}] id='{idd}' name='{name}' val='{val}' text='{text}'")
                except Exception:
                    pass

        # Try selectors in priority order
        clicked = False
        for sel in [
            "[data-testid='SPC_selectPlaceOrder']",
            "#submitOrderButtonId input",
            "input[name='placeYourOrder1']",
            "input[value*='Place your order']",
            "input[value*='Place Order']",
            "span:has-text('Place your order')",
            "button:has-text('Place your order')",
            "[id*='placeOrder'] input",
            "[id*='placeOrder']",
        ]:
            try:
                loc = p.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    print(f"  Clicking: {sel}")
                    await loc.first.click(timeout=8_000)
                    clicked = True
                    break
            except Exception as e:
                print(f"  Skip {sel[:50]}: {e}")

        if not clicked:
            # JS fallback — find any submit input near "place" text and submit its form
            print("  Trying JS form submit fallback...")
            result = await p.evaluate("""() => {
                // Try by name
                let btn = document.querySelector('[name="placeYourOrder1"]');
                if (btn) { btn.form ? btn.form.submit() : btn.click(); return 'placeYourOrder1'; }
                // Try by id pattern
                btn = document.querySelector('[id*="placeOrder"]');
                if (btn) { btn.click(); return btn.id; }
                // Try all submit inputs and find one with "place" in value
                for (const inp of document.querySelectorAll('input[type="submit"]')) {
                    if (inp.value && inp.value.toLowerCase().includes('place')) {
                        inp.form ? inp.form.submit() : inp.click();
                        return inp.value;
                    }
                }
                return null;
            }""")
            if result:
                print(f"  JS submit triggered: {result}")
                clicked = True
            else:
                raise RuntimeError("Could not find Place Order button — check /tmp/amazon_before_place_order.png")

        await p.wait_for_load_state("domcontentloaded", timeout=20_000)

        # Extract order confirmation
        order_id = ""
        order_el = await p.query_selector(
            "[data-testid='thank-you-order-id-label'], "
            "#a-page span.a-text-bold"
        )
        if order_el:
            text = await order_el.inner_text()
            id_match = re.search(r"(\d{3}-\d{7}-\d{7})", text)
            if id_match:
                order_id = id_match.group(1)

        total_el = await p.query_selector("[data-testid='order-summary-total'], .grand-total-price")
        total = (await total_el.inner_text()).strip() if total_el else "N/A"

        delivery_el = await p.query_selector("[data-testid='delivery-date'], .delivery-date-value")
        delivery_info = (await delivery_el.inner_text()).strip() if delivery_el else "N/A"

        return BrowserOrderResult(order_id=order_id, total=total, delivery_info=delivery_info)


# ---------------------------------------------------------------------------
# Context manager: launch browser session
# ---------------------------------------------------------------------------

@asynccontextmanager
async def amazon_browser_session(headless: bool = False, storage_state_path: str | None = None):
    """
    Yields an AmazonSession backed by a Playwright browser.
    headless=False lets you see what the agent is doing (recommended for first runs).
    storage_state_path: path to a saved browser session (cookies + localStorage).
    """
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                # Disable Chrome's native passkey bubble popup entirely
                "--disable-features=WebAuthentication,WebAuthenticationConditionalUI,"
                "PasswordManagerOnboarding,PasskeyAutofill,AutofillEnablePasswordManagerPromoCard",
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
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        if storage_state_path and os.path.exists(storage_state_path):
            ctx_kwargs["storage_state"] = storage_state_path

        ctx: BrowserContext = await browser.new_context(**ctx_kwargs)

        # Remove webdriver flag — Amazon detects navigator.webdriver = true
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
        """)

        page = await ctx.new_page()
        try:
            yield AmazonSession(page), ctx
        finally:
            await ctx.close()
            await browser.close()
