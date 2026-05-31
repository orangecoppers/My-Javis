from __future__ import annotations

import random
import re
import time
from abc import ABC
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urljoin, urlparse

from jarvis.models import Listing
from jarvis.safety import SafetyPolicy


PRICE_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{4,9})\s*원?")


class MarketplaceAdapter(ABC):
    marketplace: str

    def __init__(
        self,
        search_url: str,
        delay_range: tuple[float, float],
        retry_limit: int,
        safety: SafetyPolicy,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.search_url = search_url
        self.delay_range = delay_range
        self.retry_limit = retry_limit
        self.safety = safety
        self.sleep = sleep

    def collect(
        self,
        page: Any,
        query: str,
        limit: int,
        prepare: Callable[[Any, str], None] | None = None,
    ) -> list[Listing]:
        url = self.search_url.format(query=quote(query))
        self._safe_goto(page, url)
        if prepare:
            prepare(page, self.marketplace)
        if page.url != url:
            self._safe_goto(page, url)
        return self.collect_current_page(page, limit)

    def collect_current_page(self, page: Any, limit: int) -> list[Listing]:
        urls = self._candidate_urls(page)
        listings: list[Listing] = []
        for url in urls:
            if len(listings) >= limit:
                break
            listing = self._visit_with_retry(page, url)
            if listing is not None:
                listings.append(listing)
            self.sleep(random.uniform(*self.delay_range))
        return listings

    def _candidate_urls(self, page: Any) -> list[str]:
        current_url = page.url
        anchors = page.locator("a[href]")
        urls: list[str] = []
        seen: set[str] = set()
        for index in range(min(anchors.count(), 500)):
            href = anchors.nth(index).get_attribute("href")
            if not href:
                continue
            url = urljoin(current_url, href)
            if url in seen or not self.is_listing_url(url):
                continue
            self.safety.assert_allowed_url(url)
            seen.add(url)
            urls.append(url)
        return urls

    def _visit_with_retry(self, page: Any, url: str) -> Listing | None:
        for attempt in range(self.retry_limit + 1):
            try:
                self._safe_goto(page, url)
                return self.extract_listing(page)
            except Exception:
                if attempt == self.retry_limit:
                    return None
                self.sleep(0.5 * (attempt + 1))
        return None

    def _safe_goto(self, page: Any, url: str) -> None:
        self.safety.assert_allowed_url(url)
        page.goto(url, wait_until="domcontentloaded")
        self.safety.assert_allowed_url(page.url)

    def extract_listing(self, page: Any) -> Listing | None:
        title = self._meta_content(page, "meta[property='og:title']") or page.title()
        description = self._meta_content(page, "meta[property='og:description']")
        text = page.locator("body").inner_text(timeout=3_000)
        price = self.extract_price(f"{description}\n{text}")
        if not title or price is None:
            return None
        return Listing(
            marketplace=self.marketplace,
            external_id=self.external_id(page.url),
            title=title.strip()[:300],
            price=price,
            url=page.url,
            description=description.strip()[:2_000],
        )

    @staticmethod
    def extract_price(text: str) -> int | None:
        prices = []
        for matched in PRICE_PATTERN.findall(text.replace(" ", "")):
            value = int(matched.replace(",", ""))
            if 10_000 <= value <= 100_000_000:
                prices.append(value)
        return prices[0] if prices else None

    @staticmethod
    def _meta_content(page: Any, selector: str) -> str:
        locator = page.locator(selector)
        if locator.count() == 0:
            return ""
        return locator.first.get_attribute("content") or ""

    def external_id(self, url: str) -> str:
        path = urlparse(url).path.rstrip("/")
        return path.rsplit("/", maxsplit=1)[-1]

    def is_listing_url(self, url: str) -> bool:
        raise NotImplementedError
