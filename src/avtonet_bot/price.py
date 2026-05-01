from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .models import Listing


@dataclass(frozen=True)
class PriceInsight:
    is_good_price: bool
    median_price_eur: int | None
    comparable_count: int


_STOP_WORDS = {
    "dci",
    "tdi",
    "tsi",
    "hdi",
    "cdi",
    "cdti",
    "jtd",
    "xdrive",
    "quattro",
    "edition",
    "oprema",
}


def analyze_price(listing: Listing, listings: list[Listing], good_ratio: float) -> PriceInsight:
    if listing.price_eur is None:
        return PriceInsight(False, None, 0)

    comparable_prices = [
        item.price_eur
        for item in listings
        if item.id != listing.id and item.price_eur is not None and _is_comparable(listing, item)
    ]

    if len(comparable_prices) < 3:
        return PriceInsight(False, None, len(comparable_prices))

    median_price = int(statistics.median(comparable_prices))
    return PriceInsight(
        is_good_price=listing.price_eur <= median_price * good_ratio,
        median_price_eur=median_price,
        comparable_count=len(comparable_prices),
    )


def _is_comparable(left: Listing, right: Listing) -> bool:
    title_overlap = _title_similarity(left.title, right.title) >= 2
    year_close = left.year is None or right.year is None or abs(left.year - right.year) <= 2
    mileage_close = (
        left.mileage_km is None
        or right.mileage_km is None
        or abs(left.mileage_km - right.mileage_km) <= max(30_000, int(left.mileage_km * 0.35))
    )
    return title_overlap and year_close and mileage_close


def _title_similarity(left: str, right: str) -> int:
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    return len(left_tokens & right_tokens)


def _title_tokens(value: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", value.lower()))
    return {token for token in tokens if len(token) > 2 and token not in _STOP_WORDS}
