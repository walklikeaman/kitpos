"""
Address management.

For now validates via a simple normalization heuristic.
In production: integrate with Amazon's address validation endpoint
or the Playwright flow for the address suggestion dialog.
"""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class AddressValidation:
    original: str
    normalized: str | None
    is_valid: bool
    requires_confirmation: bool
    message: str


_REQUIRED_PATTERNS = [
    r"\d+",           # street number
    r"[A-Z]{2}",      # state abbreviation
    r"\d{5}",         # ZIP code
]


def validate_address(address: str) -> AddressValidation:
    """
    Basic structural validation.
    Returns requires_confirmation=True if the address looks incomplete.
    """
    if not address or len(address.strip()) < 10:
        return AddressValidation(
            original=address,
            normalized=None,
            is_valid=False,
            requires_confirmation=True,
            message="Address is missing or too short.",
        )

    missing = []
    for pat in _REQUIRED_PATTERNS:
        if not re.search(pat, address):
            missing.append(pat)

    if missing:
        return AddressValidation(
            original=address,
            normalized=None,
            is_valid=False,
            requires_confirmation=True,
            message=f"Address may be incomplete (missing: {', '.join(missing)}).",
        )

    # Normalize: collapse whitespace, title-case
    normalized = " ".join(address.split())

    changed = normalized.lower() != address.strip().lower()
    return AddressValidation(
        original=address,
        normalized=normalized,
        is_valid=True,
        requires_confirmation=changed,
        message="Address normalized." if changed else "Address looks good.",
    )
