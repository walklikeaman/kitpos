from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PLACED = "placed"
    FAILED = "failed"


class SkipReason(str, Enum):
    DELIVERY_TOO_LONG = "Delivery exceeds 4 business days"
    NOT_FOUND = "Product not found"
    AMBIGUOUS_MATCH = "Multiple candidates — requires confirmation"
    SUSPICIOUS_PRICE = "Price looks suspicious"
    BAD_SELLER = "Seller not trusted"
    SUBSCRIPTION_DETECTED = "Subscription or auto add-on detected"


@dataclass
class ParsedItem:
    query: str
    qty: int = 1


@dataclass
class PurchaseRequest:
    items: list[ParsedItem]
    ship_to: str
    raw: str = ""


@dataclass
class ProductMatch:
    asin: str
    title: str
    brand: str
    price: float
    currency: str
    seller: str
    is_amazon_fulfilled: bool
    estimated_delivery: date
    url: str
    confidence: float  # 0..1


@dataclass
class CartItem:
    item: ParsedItem
    match: ProductMatch


@dataclass
class SkippedItem:
    item: ParsedItem
    reason: SkipReason
    candidates: list[ProductMatch] = field(default_factory=list)


@dataclass
class OrderSummary:
    cart: list[CartItem]
    skipped: list[SkippedItem]
    ship_to: str
    total: float
    currency: str


@dataclass
class PlacedOrder:
    order_id: str
    total: float
    currency: str
    delivery_dates: dict[str, date]  # asin -> date
    status: OrderStatus = OrderStatus.PLACED
