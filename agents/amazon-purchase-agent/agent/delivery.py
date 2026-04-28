"""
Business-day delivery checker.

Counts weekdays between today and estimated_delivery.
US federal holidays are excluded.
"""
from __future__ import annotations
from datetime import date, timedelta

# US federal holidays 2025-2027 (add more as needed)
_US_HOLIDAYS: set[date] = {
    # 2025
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 5, 26),
    date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1), date(2025, 10, 13),
    date(2025, 11, 11), date(2025, 11, 27), date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 4), date(2026, 9, 7), date(2026, 10, 12),
    date(2026, 11, 11), date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 5, 31),
    date(2027, 6, 19), date(2027, 7, 5), date(2027, 9, 6), date(2027, 10, 11),
    date(2027, 11, 11), date(2027, 11, 25), date(2027, 12, 25),
}


def business_days_until(delivery: date, today: date | None = None) -> int:
    """Return number of business days from today (inclusive) to delivery (inclusive)."""
    start = today or date.today()
    if delivery <= start:
        return 0
    count = 0
    current = start + timedelta(days=1)
    while current <= delivery:
        if current.weekday() < 5 and current not in _US_HOLIDAYS:
            count += 1
        current += timedelta(days=1)
    return count


def is_within_limit(delivery: date, max_days: int, today: date | None = None) -> bool:
    return business_days_until(delivery, today) <= max_days
