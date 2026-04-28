"""
Browser-based procurement orchestrator.

Replaces the SP-API adapter with real Playwright automation.
Uses the same agent logic (delivery gate, confirmation, etc.)
but executes via AmazonSession instead of API calls.
"""
from __future__ import annotations
import asyncio
import re
from dataclasses import dataclass, field
from datetime import date

from agent.delivery import is_within_limit, business_days_until
from agent.address import validate_address
from browser.amazon_session import AmazonSession, amazon_browser_session, BrowserOrderResult
from config import config
from models import (
    CartItem,
    OrderSummary,
    ParsedItem,
    PlacedOrder,
    OrderStatus,
    SkipReason,
    SkippedItem,
    ProductMatch,
    PurchaseRequest,
)


@dataclass
class ResolvedAddress:
    full_name: str
    street: str
    city: str
    state: str
    zip_code: str
    phone: str = ""


def _parse_address_fields(address_str: str) -> ResolvedAddress:
    """
    Parse a free-form address string into fields.
    Expected format: "Name, Street, City, ST ZIP, [Phone]"
    or just "Street, City, ST ZIP"
    """
    parts = [p.strip() for p in address_str.split(",")]

    # Try to find ZIP and state
    zip_match = re.search(r"\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b", address_str)
    state = zip_match.group(1) if zip_match else ""
    zip_code = zip_match.group(2) if zip_match else ""

    # Find street (contains a number)
    street = ""
    city = ""
    full_name = ""
    phone = ""

    for part in parts:
        if re.search(r"^\d+\s+\w", part):  # starts with number → street
            street = part
        elif re.search(r"\+?1?\s*\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", part):  # phone
            phone = part
        elif state and state in part and zip_code and zip_code in part:
            city_part = re.sub(r"\b[A-Z]{2}\s+\d{5}.*", "", part).strip().rstrip(",").strip()
            city = city_part
        elif not street and not city and re.match(r"[A-Za-z]", part):
            full_name = part

    return ResolvedAddress(
        full_name=full_name or "Recipient",
        street=street,
        city=city,
        state=state,
        zip_code=zip_code,
        phone=phone,
    )


async def run_browser_purchase(
    request: PurchaseRequest,
    email: str,
    password: str,
    headless: bool = False,
    confirm_callback=None,  # async fn(summary_text: str) -> bool
) -> dict:
    """
    Full browser-automated purchase flow.

    confirm_callback: async function that receives summary text and returns True to confirm.
    If None, always waits for terminal input.
    """
    results = {
        "cart": [],
        "skipped": [],
        "order": None,
        "error": None,
    }

    session_file = "amazon_session.json"
    async with amazon_browser_session(headless=headless, storage_state_path=session_file) as (session, browser_ctx):
        # 1. Login (skip if saved session already authenticated)
        import os as _os
        if _os.path.exists(session_file):
            print("→ Using saved session — skipping login...")
            # Quick check if session is still valid
            await session._page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=20_000)
            nav_el = await session._page.query_selector("#nav-link-accountList-nav-line-1")
            nav_text = (await nav_el.inner_text()).strip() if nav_el else ""
            if nav_text and "sign in" not in nav_text.lower():
                print(f"  ✓ Session valid — {nav_text}")
            else:
                print("  Session expired — logging in fresh...")
                await session.login(email, password)
        else:
            print("→ Logging in to Amazon Business...")
            try:
                await session.login(email, password)
                print("  ✓ Logged in")
            except RuntimeError as e:
                print(f"  ⚠ {e}")
                print("  Complete in the browser window, then press Enter...")
                input()
                await session.resume_after_mfa()

        # 2. Set delivery ZIP so product pages show correct delivery estimates
        addr_fields = _parse_address_fields(request.ship_to)
        if addr_fields.zip_code:
            print(f"→ Setting delivery location to ZIP {addr_fields.zip_code}...")
            await session.set_delivery_zip(addr_fields.zip_code)

        # 3. Load order history + reorder list — these are the trusted sources
        print("→ Loading order history (past orders)...")
        history_items = await session.search_order_history("")  # load all; scored later per-item
        history_by_asin = {r["asin"]: r for r in history_items}
        print(f"  Found {len(history_items)} items in order history")

        print("→ Loading Reorder List...")
        reorder_items = await session.search_reorder("")  # load all
        reorder_by_asin = {r["asin"]: r for r in reorder_items}
        print(f"  Found {len(reorder_items)} items in Reorder List")

        # 3. Resolve each item
        today = date.today()
        cart_items: list[tuple[ParsedItem, dict]] = []  # (item, product_info)
        skipped: list[SkippedItem] = []

        for item in request.items:
            print(f"\n→ Resolving: {item.query}")

            # Priority 0: pinned ASIN — exact product we always want for this keyword
            q_lower = item.query.lower()
            pinned = next(
                ((asin, label) for kw, (asin, label) in config.pinned_asins.items() if kw in q_lower),
                None,
            )
            if pinned:
                pinned_asin, pinned_label = pinned
                print(f"  [Pinned] {pinned_label}  (ASIN {pinned_asin})")
                best = {"asin": pinned_asin, "title": pinned_label, "price": 0.0, "seller": "Amazon", "score": 1.0}
                source = "Pinned"
            else:
                best = None
                source = ""

            if not best:
                # Priority 1: order history (exact items we've bought before)
                history_matches = await session.search_order_history(item.query)
                if history_matches:
                    best = history_matches[0]
                    source = "OrderHistory"
                else:
                    # Priority 2: reorder list
                    reorder_matches = await session.search_reorder(item.query)
                    if reorder_matches:
                        best = reorder_matches[0]
                        source = "Reorder"
                    else:
                        # Priority 3: regular search
                        regular = await session.search_regular(item.query)
                        if not regular:
                            print(f"  ✗ Not found: {item.query}")
                            skipped.append(SkippedItem(item=item, reason=SkipReason.NOT_FOUND))
                            continue
                        best = regular[0]
                        source = "Search"

            confidence = best.get("score", 0)
            print(f"  [{source}] {best['title']}  conf={confidence:.0%}")

            if confidence < config.min_match_confidence:
                print(f"  ⚠ Low confidence — stopping for confirmation")
                skipped.append(SkippedItem(
                    item=item,
                    reason=SkipReason.AMBIGUOUS_MATCH,
                    candidates=[
                        ProductMatch(
                            asin=r["asin"], title=r["title"], brand="",
                            price=r["price"], currency="USD", seller=r.get("seller", ""),
                            is_amazon_fulfilled=True, estimated_delivery=today,
                            url=f"https://www.amazon.com/dp/{r['asin']}",
                            confidence=r.get("score", 0),
                        )
                        for r in [best][:3]
                    ],
                ))
                continue

            # Get delivery + seller details (use search card data if available)
            details = await session.get_product_details(best["asin"], prefetched=best)
            delivery_date = details["delivery_date"]
            seller = details["seller"] or best.get("seller", "Unknown")
            price = details["price"] or best.get("price", 0)

            if delivery_date is None:
                print(f"  ⚠ Could not determine delivery date — skipping")
                skipped.append(SkippedItem(item=item, reason=SkipReason.DELIVERY_TOO_LONG))
                continue

            days = business_days_until(delivery_date, today)
            print(f"  Delivery: {delivery_date}  ({days} business days)  Seller: {seller}  ${price:.2f}")

            if not is_within_limit(delivery_date, config.max_delivery_business_days, today):
                print(f"  ✗ Delivery too long ({days} days > {config.max_delivery_business_days})")
                skipped.append(SkippedItem(item=item, reason=SkipReason.DELIVERY_TOO_LONG))
                continue

            if details.get("has_subscription"):
                print(f"  ✗ Subscription detected — skipping")
                skipped.append(SkippedItem(item=item, reason=SkipReason.SUBSCRIPTION_DETECTED))
                continue

            cart_items.append((item, {**best, "delivery_date": delivery_date, "seller": seller, "price": price}))
            print(f"  ✓ Added to cart plan")

        if not cart_items:
            print("\n⚠ No valid items to order.")
            results["skipped"] = skipped
            return results

        # 4. Print summary and confirm
        print("\n" + "="*60)
        print("READY TO PLACE ORDER")
        print("="*60)
        for item, prod in cart_items:
            print(f"  • {prod['title']} × {item.qty}  ${prod['price']:.2f}  → {prod['delivery_date']}")
        for sk in skipped:
            print(f"  SKIP: {sk.item.query} — {sk.reason.value}")
        total = sum(p["price"] * i.qty for i, p in cart_items)
        print(f"\nShipping: {request.ship_to}")
        print(f"Total: ${total:.2f}")
        print("="*60)

        if confirm_callback:
            confirmed = await confirm_callback(f"${total:.2f} for {len(cart_items)} items")
        else:
            answer = input("\nType 'Confirm order' to proceed: ").strip().lower()
            confirmed = answer in ("confirm order", "place order", "confirm", "yes")

        if not confirmed:
            print("Order cancelled.")
            results["skipped"] = skipped
            return results

        # 5. Add items to cart
        print("\n→ Adding items to cart...")
        await session.go_to_cart()  # go there first to clear state, then navigate away

        for item, prod in cart_items:
            asin = prod["asin"]
            in_reorder = asin in reorder_by_asin or asin in history_by_asin
            if in_reorder:
                await session._page.goto(
                    "https://www.amazon.com/gp/buy/reorder/handlers/display.html",
                    wait_until="domcontentloaded",
                )
                ok = await session.add_from_reorder(asin, item.qty)
            else:
                ok = await session.add_to_cart(asin, item.qty)
            print(f"  {'✓' if ok else '✗'} {prod['title']} × {item.qty}")

        # 6. Checkout
        print("\n→ Proceeding to checkout...")
        await session.go_to_cart()
        await session.proceed_to_checkout()

        # 7. Address
        print("→ Setting delivery address...")
        addr = _parse_address_fields(request.ship_to)
        await session.select_or_create_address(
            full_name=addr.full_name,
            street=addr.street,
            city=addr.city,
            state=addr.state,
            zip_code=addr.zip_code,
            phone=addr.phone,
        )

        # 8. Delivery option
        await session.select_fastest_free_delivery()

        # 9. Place order
        print("→ Placing order...")
        order_result = await session.place_order()

        print(f"\n✓ ORDER PLACED")
        print(f"  Order ID: {order_result.order_id}")
        print(f"  Total: {order_result.total}")
        print(f"  Delivery: {order_result.delivery_info}")

        results["order"] = order_result
        results["cart"] = cart_items
        results["skipped"] = skipped

    return results
