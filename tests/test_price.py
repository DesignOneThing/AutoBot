from avtonet_bot.models import Listing
from avtonet_bot.price import analyze_price


def _listing(listing_id: str, price: int, year: int = 2019, mileage: int = 100_000) -> Listing:
    return Listing(
        id=listing_id,
        url=f"https://example.test/{listing_id}",
        title="Volkswagen Golf 1.6 TDI",
        price_eur=price,
        year=year,
        mileage_km=mileage,
    )


def test_analyze_price_marks_listing_below_median() -> None:
    target = _listing("target", 10_000)
    listings = [
        target,
        _listing("a", 14_000),
        _listing("b", 15_000),
        _listing("c", 16_000),
        _listing("d", 17_000),
    ]

    insight = analyze_price(target, listings, good_ratio=0.88)

    assert insight.is_good_price is True
    assert insight.median_price_eur == 15500
    assert insight.comparable_count == 4
