from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from .models import Listing


@dataclass(frozen=True)
class ScrapeResult:
    listings: list[Listing]
    pages_scanned: int


class AvtoNetScraper:
    def __init__(self, timeout_seconds: int = 30, max_pages: int = 3) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_pages = max_pages

    async def scrape(self, url: str) -> ScrapeResult:
        listings_by_id: dict[str, Listing] = {}
        next_url: str | None = url
        pages_scanned = 0

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "sl-SI,sl;q=0.9,en;q=0.8",
            },
        ) as client:
            while next_url and pages_scanned < self.max_pages:
                response = await client.get(next_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                for listing in parse_listings(response.text, str(response.url)):
                    listings_by_id.setdefault(listing.id, listing)
                pages_scanned += 1
                next_url = _find_next_page_url(soup, str(response.url))

        return ScrapeResult(list(listings_by_id.values()), pages_scanned)


def parse_listings(html: str, base_url: str = "https://www.avto.net/") -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    listings: dict[str, Listing] = {}

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        if not _looks_like_listing_url(href):
            continue

        url = _normalize_url(urljoin(base_url, href))
        card = _find_listing_card(anchor)
        text = _clean_text(card.get_text(" ", strip=True) if card else anchor.get_text(" ", strip=True))
        title = _extract_title(anchor, card)
        if not title:
            continue

        listing = Listing(
            id=_listing_id(url),
            url=url,
            title=title,
            price_eur=_extract_price(text),
            year=_extract_year(text),
            mileage_km=_extract_mileage(text),
            location=_extract_location(text),
            image_url=_extract_image_url(card, base_url),
            raw_text=text,
        )
        listings[listing.id] = listing

    return list(listings.values())


def _looks_like_listing_url(href: str) -> bool:
    lower = href.lower()
    if any(skip in lower for skip in ("javascript:", "mailto:", "tel:", "#")):
        return False
    return (
        "ad.asp" in lower
        or "details" in lower
        or "oglas" in lower
        or bool(re.search(r"[?&](id|oglasid|adid)=\d+", lower))
    )


def _find_listing_card(anchor: Tag) -> Tag | None:
    selectors = [
        "[class*=oglas]",
        "[class*=advert]",
        "[class*=listing]",
        "[class*=result]",
        "[class*=card]",
        "tr",
        "article",
    ]
    for selector in selectors:
        found = anchor.find_parent(selector)
        if isinstance(found, Tag):
            return found

    parent = anchor.parent
    for _ in range(4):
        if not isinstance(parent, Tag):
            break
        if len(parent.get_text(" ", strip=True)) > 40:
            return parent
        parent = parent.parent
    return anchor


def _extract_title(anchor: Tag, card: Tag | None) -> str:
    candidates = [
        anchor.get_text(" ", strip=True),
        anchor.get("title", ""),
    ]
    if card:
        for selector in ("h1", "h2", "h3", "h4", "[class*=title]", "[class*=naslov]"):
            node = card.select_one(selector)
            if node:
                candidates.append(node.get_text(" ", strip=True))

    for candidate in candidates:
        title = _clean_text(str(candidate))
        if len(title) >= 4 and not re.fullmatch(r"[\d\s.,€]+", title):
            return title
    return ""


def _extract_price(text: str) -> int | None:
    matches = re.findall(r"(\d{1,3}(?:[.\s]\d{3})*|\d+)\s*(?:€|EUR|eur)", text)
    if not matches:
        return None
    values = [_to_int(match) for match in matches]
    realistic = [value for value in values if 100 <= value <= 500_000]
    return realistic[0] if realistic else None


def _extract_year(text: str) -> int | None:
    matches = [int(match) for match in re.findall(r"\b(19[8-9]\d|20[0-3]\d)\b", text)]
    return matches[0] if matches else None


def _extract_mileage(text: str) -> int | None:
    match = re.search(
        r"(?:^|\D)(\d{1,3}(?:[.\s]\d{3})+|\d{4,6})\s*km\b",
        text,
        flags=re.IGNORECASE,
    )
    return _to_int(match.group(1)) if match else None


def _extract_location(text: str) -> str | None:
    match = re.search(r"\b(?:kraj|lokacija|okraj)\s*[:\-]?\s*([A-ZČŠŽa-zčšž\s-]{3,40})", text)
    return _clean_text(match.group(1)) if match else None


def _extract_image_url(card: Tag | None, base_url: str) -> str | None:
    if not card:
        return None
    image = card.find("img")
    if not isinstance(image, Tag):
        return None
    src = image.get("src") or image.get("data-src") or image.get("data-original")
    return urljoin(base_url, str(src)) if src else None


def _find_next_page_url(soup: BeautifulSoup, current_url: str) -> str | None:
    rel_next = soup.find("a", rel=lambda value: value and "next" in value)
    if isinstance(rel_next, Tag) and rel_next.get("href"):
        return urljoin(current_url, str(rel_next["href"]))

    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True).lower()
        if text in {"naprej", "naslednja", "next", ">"} or "naprej" in text:
            return urljoin(current_url, str(anchor["href"]))
    return _increment_page_param(current_url)


def _increment_page_param(current_url: str) -> str | None:
    parsed = urlparse(current_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key in ("page", "stran", "p", "pg"):
        if key in params and params[key].isdigit():
            params[key] = str(int(params[key]) + 1)
            return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
    if not params:
        return None
    return None


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(fragment=""))


def _listing_id(url: str) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query))
    for key in ("id", "oglasid", "adid"):
        if params.get(key):
            return params[key]
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _to_int(value: str) -> int:
    return int(re.sub(r"\D", "", value))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
