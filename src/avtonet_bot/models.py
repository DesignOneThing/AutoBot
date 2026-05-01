from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Listing:
    id: str
    url: str
    title: str
    price_eur: int | None = None
    year: int | None = None
    mileage_km: int | None = None
    location: str | None = None
    image_url: str | None = None
    raw_text: str = ""


@dataclass(frozen=True)
class Search:
    id: int
    chat_id: int
    name: str
    url: str
    interval_seconds: int
    good_price_enabled: bool
    is_active: bool = True
