"""
Entry points:
  python main.py serve                        — start webhook server
  python main.py buy "<msg>"                  — CLI with mock search (no browser)
  python main.py browser "<msg>"              — real browser, visible window
  python main.py browser-headless "<msg>"     — real browser, headless

  python main.py merchant <MERCHANT_ID> "<items msg>"
      — look up merchant from KIT Dashboard, then purchase on Amazon Business
        Example:
          python main.py merchant 201100312345 "Scanner × 1, Printer × 1, Cash Drawer × 1"

  python main.py lookup <MERCHANT_ID>         — just fetch & print merchant data
"""
from __future__ import annotations
import sys


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_env():
    from dotenv import load_dotenv
    load_dotenv()


def _amazon_creds():
    import os
    email    = os.getenv("AMAZON_BUSINESS_EMAIL", "")
    password = os.getenv("AMAZON_PASSWORD", "")
    if not email or not password:
        print("Set AMAZON_BUSINESS_EMAIL and AMAZON_PASSWORD in .env")
        sys.exit(1)
    return email, password


def _kit_creds():
    import os
    from kit.models import KitCredentials
    email    = os.getenv("KIT_EMAIL", "")
    password = os.getenv("KIT_PASSWORD", "")
    if not email or not password:
        print("Set KIT_EMAIL and KIT_PASSWORD in .env")
        sys.exit(1)
    return KitCredentials(email=email, password=password)


# ── Commands ──────────────────────────────────────────────────────────────────

def serve():
    import uvicorn
    from triggers.webhook import app
    uvicorn.run(app, host="0.0.0.0", port=8080)


def cli_buy(message: str):
    from agent.parser import parse_request
    from agent.orchestrator import ProcurementOrchestrator

    req = parse_request(message)
    if not req.ship_to:
        print("No shipping address found. Please include 'Ship to: <address>' in your message.")
        return

    orchestrator = ProcurementOrchestrator(req)
    summary, issues = orchestrator.build_summary()
    print(orchestrator.format_summary(summary, issues))

    if orchestrator.can_auto_place(summary, issues):
        order = orchestrator.place_order(summary)
        print("\n" + orchestrator.format_placed(order))
        return

    if not summary.cart:
        return

    answer = input("\nType 'Confirm order' to place, or press Enter to cancel: ").strip().lower()
    if answer in ("confirm order", "place order"):
        order = orchestrator.place_order(summary)
        print("\n" + orchestrator.format_placed(order))
    else:
        print("Order cancelled.")


def cli_browser(message: str, headless: bool = False):
    import asyncio
    from agent.parser import parse_request
    from browser.browser_orchestrator import run_browser_purchase

    _load_env()
    email, password = _amazon_creds()

    req = parse_request(message)
    if not req.ship_to:
        print("No shipping address found. Include 'Ship to: <address>' in your message.")
        return

    asyncio.run(run_browser_purchase(req, email, password, headless=headless))


def cli_lookup(merchant_id: str):
    """Fetch merchant data from KIT Dashboard and print it."""
    import asyncio
    from kit.merchant_lookup import MerchantLookupService
    from pathlib import Path

    _load_env()
    creds = _kit_creds()
    creds_headless = True  # lookup is always headless

    service = MerchantLookupService(creds, headless=creds_headless, debug_dir=Path("debug"))
    print(f"→ Looking up merchant {merchant_id} in KIT Dashboard...")
    result = asyncio.run(service.lookup_by_id(merchant_id))
    print("\n" + result.summary())
    return result


def cli_merchant_order(merchant_id: str, items_message: str, headless: bool = False):
    """
    Full flow:
      1. Look up merchant in KIT Dashboard → get name, address, phone
      2. Build Amazon purchase request
      3. Run browser purchase flow
    """
    import asyncio
    from kit.merchant_lookup import MerchantLookupService
    from agent.parser import parse_request
    from browser.browser_orchestrator import run_browser_purchase
    from pathlib import Path
    from models import PurchaseRequest

    _load_env()
    kit_creds     = _kit_creds()
    email, password = _amazon_creds()

    # Step 1: merchant data
    print(f"→ Fetching merchant data for ID {merchant_id}...")
    service = MerchantLookupService(kit_creds, headless=True, debug_dir=Path("debug"))
    merchant = asyncio.run(service.lookup_by_id(merchant_id))
    print("\nMerchant found:")
    print(merchant.summary())

    if not merchant.address:
        print("\n⚠  No address found for merchant. Cannot place order.")
        sys.exit(1)

    # Step 2: build ship_to from merchant data
    # Format: "Principal Name, Street, City, ST ZIP, Phone"
    ship_to = merchant.to_ship_to()
    print(f"\n→ Ship to: {ship_to}")

    # Step 3: parse items from message (no ship_to needed — we have it from KIT)
    full_message = f"{items_message}\nShip to: {ship_to}"
    req = parse_request(full_message)
    if not req.items:
        print("No items found in message. Example: 'Scanner × 2, Printer × 1'")
        sys.exit(1)

    # Step 4: run Amazon purchase
    asyncio.run(run_browser_purchase(req, email, password, headless=headless))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _load_env()
    args = sys.argv[1:]

    if not args or args[0] == "serve":
        serve()

    elif args[0] == "buy" and len(args) > 1:
        cli_buy(" ".join(args[1:]))

    elif args[0] == "browser" and len(args) > 1:
        cli_browser(" ".join(args[1:]), headless=False)

    elif args[0] == "browser-headless" and len(args) > 1:
        cli_browser(" ".join(args[1:]), headless=True)

    elif args[0] == "lookup" and len(args) > 1:
        cli_lookup(args[1])

    elif args[0] == "merchant" and len(args) > 2:
        merchant_id   = args[1]
        items_message = " ".join(args[2:])
        cli_merchant_order(merchant_id, items_message, headless=False)

    elif args[0] == "merchant-headless" and len(args) > 2:
        merchant_id   = args[1]
        items_message = " ".join(args[2:])
        cli_merchant_order(merchant_id, items_message, headless=True)

    else:
        print(
            "Usage:\n"
            "  python main.py serve\n"
            "  python main.py buy \"<message>\"\n"
            "  python main.py browser \"<message>\"\n"
            "  python main.py browser-headless \"<message>\"\n"
            "  python main.py lookup <MERCHANT_ID>\n"
            "  python main.py merchant <MERCHANT_ID> \"<items>\"\n"
            "  python main.py merchant-headless <MERCHANT_ID> \"<items>\"\n"
        )
