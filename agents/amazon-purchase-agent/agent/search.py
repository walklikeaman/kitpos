"""
Product search against Amazon SP-API (Catalog Items API).

Falls back to a mock adapter when SP-API credentials are not configured
so the agent can be tested end-to-end without real credentials.
"""
from __future__ import annotations
import os
from datetime import date, timedelta
from typing import Protocol

import anthropic

from config import config
from models import ParsedItem, ProductMatch


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _score_match(query: str, title: str, brand: str) -> float:
    """Keyword overlap score (0..1) — strips punctuation before comparison."""
    import re as _re
    def tokenize(s: str) -> set[str]:
        return set(_re.sub(r"[^\w\s]", " ", s.lower()).split())

    query_tokens = tokenize(query)
    candidate_tokens = tokenize(title + " " + brand)
    if not query_tokens:
        return 0.0
    overlap = query_tokens & candidate_tokens
    return len(overlap) / len(query_tokens)


# ---------------------------------------------------------------------------
# SP-API adapter (real)
# ---------------------------------------------------------------------------

class _SPAPIAdapter:
    """Thin wrapper around Amazon SP-API Catalog + Pricing endpoints."""

    BASE_URL = "https://sellingpartnerapi-na.amazon.com"

    def __init__(self) -> None:
        self._token: str | None = None

    def _get_access_token(self) -> str:
        import urllib.request, urllib.parse, json as _json
        payload = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": config.sp_api_refresh_token,
            "client_id": config.sp_api_client_id,
            "client_secret": config.sp_api_client_secret,
        }).encode()
        req = urllib.request.Request(
            "https://api.amazon.com/auth/o2/token",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return _json.loads(resp.read())["access_token"]

    def search(self, query: str, marketplace_id: str) -> list[dict]:
        import urllib.request, urllib.parse, json as _json
        token = self._get_access_token()
        params = urllib.parse.urlencode({
            "keywords": query,
            "marketplaceIds": marketplace_id,
            "includedData": "summaries,attributes",
        })
        req = urllib.request.Request(
            f"{self.BASE_URL}/catalog/2022-04-01/items?{params}",
            headers={"x-amz-access-token": token, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            return _json.loads(resp.read()).get("items", [])


# ---------------------------------------------------------------------------
# Mock adapter (for dev / CI)
# ---------------------------------------------------------------------------

class _MockAdapter:
    _CATALOG: list[dict] = [
        {
            "asin": "B09XY12345",
            "title": "Symcode 2D Barcode Scanner USB Wired",
            "brand": "Symcode",
            "price": 29.99,
            "seller": "Amazon.com",
            "is_amazon_fulfilled": True,
            "delivery_offset_days": 2,
        },
        {
            "asin": "B08THERMAL1",
            "title": "Volcora Thermal Receipt Printer USB Bluetooth 80mm",
            "brand": "Volcora",
            "price": 79.99,
            "seller": "Amazon Business",
            "is_amazon_fulfilled": True,
            "delivery_offset_days": 3,
        },
        {
            "asin": "B07SLOW001",
            "title": "Generic USB Barcode Reader",
            "brand": "Generic",
            "price": 15.99,
            "seller": "ThirdPartySeller",
            "is_amazon_fulfilled": False,
            "delivery_offset_days": 7,
        },
    ]

    def search(self, query: str, _marketplace_id: str) -> list[dict]:
        q = query.lower()
        return [p for p in self._CATALOG if any(w in p["title"].lower() for w in q.split())]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def _make_adapter():
    if config.sp_api_client_id and config.sp_api_refresh_token:
        return _SPAPIAdapter()
    return _MockAdapter()


def search_product(item: ParsedItem) -> list[ProductMatch]:
    """
    Search for a product and return ranked candidates.
    Returns empty list if nothing found.
    """
    adapter = _make_adapter()
    raw_results = adapter.search(item.query, config.sp_api_marketplace_id)

    matches: list[ProductMatch] = []
    today = date.today()

    for r in raw_results:
        # SP-API returns structured dicts; mock already provides them.
        title = r.get("title", "")
        brand = r.get("brand", "")
        confidence = _score_match(item.query, title, brand)

        delivery_offset = r.get("delivery_offset_days", 5)
        estimated_delivery = today + timedelta(days=delivery_offset)

        matches.append(ProductMatch(
            asin=r["asin"],
            title=title,
            brand=brand,
            price=float(r.get("price", 0)),
            currency=r.get("currency", "USD"),
            seller=r.get("seller", ""),
            is_amazon_fulfilled=r.get("is_amazon_fulfilled", False),
            estimated_delivery=estimated_delivery,
            url=f"https://www.amazon.com/dp/{r['asin']}",
            confidence=confidence,
        ))

    # Sort by confidence descending
    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches
