"""
Main procurement orchestrator.

Flow:
  parse → validate address → search+match → delivery gate →
  cart validate → build summary → await confirmation → place order
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Callable

from agent.address import validate_address
from agent.delivery import is_within_limit
from agent.search import search_product
from config import config
from models import (
    CartItem,
    OrderSummary,
    ParsedItem,
    PlacedOrder,
    ProductMatch,
    PurchaseRequest,
    SkipReason,
    SkippedItem,
)


# ---------------------------------------------------------------------------
# Seller trust check
# ---------------------------------------------------------------------------

def _is_trusted_seller(match: ProductMatch) -> bool:
    if match.is_amazon_fulfilled:
        return True
    return any(s.lower() in match.seller.lower() for s in config.trusted_sellers)


def _has_suspicious_price(match: ProductMatch) -> bool:
    # Flag items that are free or suspiciously cheap (< $0.50) or unreasonably expensive
    return match.price < 0.5


# ---------------------------------------------------------------------------
# Single-item resolution
# ---------------------------------------------------------------------------

@dataclass
class ItemResolution:
    cart_item: CartItem | None = None
    skipped: SkippedItem | None = None


def resolve_item(item: ParsedItem) -> ItemResolution:
    candidates = search_product(item)

    if not candidates:
        return ItemResolution(skipped=SkippedItem(item=item, reason=SkipReason.NOT_FOUND))

    best = candidates[0]

    # Ambiguous match — surface candidates to user
    if best.confidence < config.min_match_confidence:
        return ItemResolution(
            skipped=SkippedItem(item=item, reason=SkipReason.AMBIGUOUS_MATCH, candidates=candidates[:3])
        )

    # Delivery gate
    if not is_within_limit(best.estimated_delivery, config.max_delivery_business_days):
        return ItemResolution(skipped=SkippedItem(item=item, reason=SkipReason.DELIVERY_TOO_LONG))

    # Price sanity
    if _has_suspicious_price(best):
        return ItemResolution(skipped=SkippedItem(item=item, reason=SkipReason.SUSPICIOUS_PRICE))

    # Seller trust
    if not _is_trusted_seller(best):
        return ItemResolution(skipped=SkippedItem(item=item, reason=SkipReason.BAD_SELLER))

    return ItemResolution(cart_item=CartItem(item=item, match=best))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ProcurementOrchestrator:
    def __init__(self, request: PurchaseRequest) -> None:
        self.request = request

    def build_summary(self) -> tuple[OrderSummary, list[str]]:
        """
        Resolve all items and return an OrderSummary plus any blocking issues
        that require human input before proceeding.
        """
        cart: list[CartItem] = []
        skipped: list[SkippedItem] = []
        issues: list[str] = []

        # Address validation
        addr = validate_address(self.request.ship_to)
        if not addr.is_valid:
            issues.append(f"Address invalid: {addr.message}")
        elif addr.requires_confirmation:
            issues.append(f"Address was normalized: '{addr.original}' → '{addr.normalized}'. Please confirm.")

        resolved_address = addr.normalized or self.request.ship_to

        # Resolve each item
        for item in self.request.items:
            resolution = resolve_item(item)
            if resolution.cart_item:
                cart.append(resolution.cart_item)
            else:
                skipped.append(resolution.skipped)
                if resolution.skipped.reason == SkipReason.AMBIGUOUS_MATCH:
                    issues.append(f"'{item.query}': multiple candidates found, please clarify.")

        total = sum(ci.match.price * ci.item.qty for ci in cart)

        summary = OrderSummary(
            cart=cart,
            skipped=skipped,
            ship_to=resolved_address,
            total=round(total, 2),
            currency="USD",
        )
        return summary, issues

    def format_summary(self, summary: OrderSummary, issues: list[str]) -> str:
        lines: list[str] = []

        if issues:
            lines.append("**⚠️ Issues requiring your attention:**")
            for issue in issues:
                lines.append(f"  • {issue}")
            lines.append("")

        if summary.cart:
            lines.append("**Ready to place order**\n")
            lines.append("Items:")
            for ci in summary.cart:
                delivery_str = ci.match.estimated_delivery.strftime("%b %d")
                lines.append(
                    f"  • {ci.match.title} × {ci.item.qty}  —  "
                    f"${ci.match.price:.2f} ea  |  Delivery: {delivery_str}  |  Seller: {ci.match.seller}"
                )

        if summary.skipped:
            lines.append("\nSkipped:")
            for sk in summary.skipped:
                lines.append(f"  • {sk.item.query} → {sk.reason.value}")
                if sk.candidates:
                    lines.append("    Candidates:")
                    for c in sk.candidates:
                        lines.append(f"      - [{c.asin}] {c.title}  ${c.price:.2f}  (confidence: {c.confidence:.0%})")

        lines.append(f"\nShipping: {summary.ship_to}")
        lines.append(f"Total: ${summary.total:.2f} {summary.currency}")

        if summary.cart and not issues:
            lines.append("\nType **Confirm order** or **Place order** to proceed.")
        elif summary.cart and issues:
            lines.append("\nResolve issues above, then type **Confirm order** to proceed.")
        else:
            lines.append("\nNo items can be ordered at this time.")

        return "\n".join(lines)

    def can_auto_place(self, summary: OrderSummary, issues: list[str]) -> bool:
        """True only when ALL autonomy conditions are met."""
        if issues:
            return False
        if summary.skipped:
            return False
        for ci in summary.cart:
            if ci.match.asin not in config.allowlist_asins:
                return False
        return True

    def place_order(self, summary: OrderSummary) -> PlacedOrder:
        """
        Submit the order via SP-API (or mock).
        In production: POST to /orders/v0/orders
        """
        # TODO: replace with real SP-API CreateOrder call
        import random, string
        fake_id = "112-" + "".join(random.choices(string.digits, k=7)) + "-" + "".join(random.choices(string.digits, k=7))
        delivery_dates = {ci.match.asin: ci.match.estimated_delivery for ci in summary.cart}
        return PlacedOrder(
            order_id=fake_id,
            total=summary.total,
            currency=summary.currency,
            delivery_dates=delivery_dates,
        )

    def format_placed(self, order: PlacedOrder) -> str:
        delivery_lines = "\n".join(
            f"  • {asin}: {d.strftime('%b %d')}" for asin, d in order.delivery_dates.items()
        )
        return (
            f"**Order placed ✓**\n"
            f"Order ID: `{order.order_id}`\n"
            f"Total: ${order.total:.2f} {order.currency}\n"
            f"Delivery:\n{delivery_lines}"
        )
