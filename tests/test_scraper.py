from avtonet_bot.scraper import parse_listings


def test_parse_listings_extracts_core_fields() -> None:
    html = """
    <html>
      <body>
        <div class="oglas-card">
          <a href="/Ads/ad.asp?id=123456">Volkswagen Golf 1.6 TDI</a>
          <span>2019</span>
          <span>117.000 km</span>
          <strong>14.990 €</strong>
          <img src="/images/golf.jpg" />
        </div>
      </body>
    </html>
    """

    listings = parse_listings(html, "https://www.avto.net/")

    assert len(listings) == 1
    assert listings[0].id == "123456"
    assert listings[0].title == "Volkswagen Golf 1.6 TDI"
    assert listings[0].price_eur == 14990
    assert listings[0].year == 2019
    assert listings[0].mileage_km == 117000
    assert listings[0].image_url == "https://www.avto.net/images/golf.jpg"
