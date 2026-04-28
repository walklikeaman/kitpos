"""
Parse a free-text purchase request into a PurchaseRequest.

Uses the Claude API so the user can write naturally:
  "Buy 2 barcode scanners and a thermal printer, ship to 123 Main St, NY"
"""
from __future__ import annotations
import json
import re
from typing import Optional

import anthropic

from config import config
from models import ParsedItem, PurchaseRequest

_client = anthropic.Anthropic(api_key=config.anthropic_api_key)

_SYSTEM = """\
You are a procurement request parser. Extract a JSON object from the user's message.

Output format (strict JSON, no markdown):
{
  "items": [
    {"query": "<product name>", "qty": <number>}
  ],
  "ship_to": "<full address or empty string>"
}

Rules:
- If qty is not mentioned, use 1.
- ship_to should be the complete address as written. Empty string if not mentioned.
- query should preserve the brand name and key specs (model, connectivity, etc.).
"""


def _regex_parse(raw: str) -> PurchaseRequest:
    """
    Fallback parser using regex — no API key needed.
    Handles formats like:
      - Product name x 2
      - Product name × 2
      - Product name (qty: 2)
    And "Ship to: ..." blocks.
    """
    lines = raw.splitlines()
    items: list[ParsedItem] = []
    ship_to_lines: list[str] = []
    in_ship = False

    for line in lines:
        line = line.strip().lstrip("-*•").strip()
        if not line:
            continue

        low = line.lower()
        if re.match(r"ship\s+to\s*:", low) or re.match(r"доставить\s+по\s*:", low):
            in_ship = True
            after = re.sub(r"(?i)ship\s+to\s*:\s*", "", line).strip()
            if after:
                ship_to_lines.append(after)
            continue

        if in_ship:
            ship_to_lines.append(line)
            continue

        # Skip header lines
        if re.match(r"(?i)^(buy|order|purchase|items?)\s*:?\s*$", line):
            continue

        # Extract qty: "Product name x 2" or "Product name × 2" or "2x Product"
        qty = 1
        # "x N" or "× N" at end
        m = re.search(r"[x×]\s*(\d+)\s*$", line, re.IGNORECASE)
        if m:
            qty = int(m.group(1))
            line = line[:m.start()].strip().rstrip("(").strip()
        else:
            # "N x" at start
            m2 = re.match(r"^(\d+)\s*[x×]\s+(.+)", line, re.IGNORECASE)
            if m2:
                qty = int(m2.group(1))
                line = m2.group(2).strip()

        if line:
            items.append(ParsedItem(query=line, qty=qty))

    return PurchaseRequest(
        items=items,
        ship_to=", ".join(ship_to_lines).strip(),
        raw=raw,
    )


def parse_request(raw: str) -> PurchaseRequest:
    """Parse free-text into a structured PurchaseRequest.
    Uses Claude API if key is set, otherwise falls back to regex parser.
    """
    if not config.anthropic_api_key:
        return _regex_parse(raw)

    msg = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_SYSTEM,
        messages=[{"role": "user", "content": raw}],
    )
    text = msg.content[0].text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    data = json.loads(text)
    items = [ParsedItem(query=i["query"], qty=int(i.get("qty", 1))) for i in data["items"]]
    return PurchaseRequest(items=items, ship_to=data.get("ship_to", ""), raw=raw)
