from __future__ import annotations

import random
import re
import time
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urljoin, urlparse

from jarvis.models import Listing
from jarvis.safety import SafetyPolicy


PRICE_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{4,9})\s*원?")


@dataclass(frozen=True, slots=True)
class CollectionDebug:
    marketplace: str
    search_url: str
    final_url: str
    anchor_count: int
    candidate_count: int
    candidate_urls: list[str]
    extraction_results: list[dict[str, object]]


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
        self.last_debug: CollectionDebug | None = None

    def search_page_url(self, query: str) -> str:
        return self.search_url.format(query=quote(query))

    def collect(
        self,
        page: Any,
        query: str,
        limit: int,
        prepare: Callable[[Any, str], None] | None = None,
    ) -> list[Listing]:
        url = self.search_page_url(query)
        self._safe_goto(page, url)
        self._wait_for_search_results(page)
        self._scroll_for_results(page)
        if prepare:
            prepare(page, self.marketplace)
        if page.url != url:
            self._safe_goto(page, url)
            self._wait_for_search_results(page)
            self._scroll_for_results(page)
        return self.collect_current_page(page, limit)

    def collect_current_page(self, page: Any, limit: int) -> list[Listing]:
        urls = self._candidate_urls(page)
        listings: list[Listing] = []
        extraction_results: list[dict[str, object]] = []
        for url in urls:
            if len(listings) >= limit:
                break
            listing = self._visit_with_retry(page, url)
            if listing is not None:
                listings.append(listing)
                extraction_results.append(
                    {"url": url, "ok": True, "title": listing.title, "price": listing.price}
                )
            else:
                extraction_results.append({"url": url, "ok": False, "reason": "extract_failed"})
            self.sleep(random.uniform(*self.delay_range))
        self.last_debug = CollectionDebug(
            marketplace=self.marketplace,
            search_url=page.url,
            final_url=page.url,
            anchor_count=self._anchor_count(page),
            candidate_count=len(urls),
            candidate_urls=urls[:10],
            extraction_results=extraction_results[:10],
        )
        return listings

    def debug_search(self, page: Any, query: str, limit: int = 3) -> dict[str, object]:
        url = self.search_page_url(query)
        self._safe_goto(page, url)
        self._wait_for_search_results(page)
        self._scroll_for_results(page)
        urls = self._candidate_urls(page)
        results: list[dict[str, object]] = []
        for candidate_url in urls[:limit]:
            listing = self._visit_with_retry(page, candidate_url)
            if listing is None:
                results.append({"url": candidate_url, "ok": False, "reason": "extract_failed"})
                continue
            results.append(
                {
                    "url": candidate_url,
                    "ok": True,
                    "title": listing.title,
                    "price": listing.price,
                    "description": listing.description[:200],
                }
            )
        return {
            "marketplace": self.marketplace,
            "search_url": url,
            "final_url": page.url,
            "anchor_count": self._anchor_count(page),
            "candidate_count": len(urls),
            "candidate_urls": urls[:10],
            "extraction_results": results,
        }

    def _wait_for_search_results(self, page: Any) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass
        try:
            page.wait_for_selector("a[href]", timeout=5_000)
        except Exception:
            pass

    def _scroll_for_results(self, page: Any, scroll_count: int = 5) -> None:
        for _ in range(scroll_count):
            try:
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(600)
            except Exception:
                return

    def _candidate_urls(self, page: Any) -> list[str]:
        current_url = page.url
        anchors = page.locator("a[href]")
        urls: list[str] = []
        seen: set[str] = set()
        for index in range(min(anchors.count(), 700)):
            href = anchors.nth(index).get_attribute("href")
            if not href:
                continue
            url = self.normalize_listing_url(urljoin(current_url, href))
            if url in seen or not self.is_listing_url(url):
                continue
            self.safety.assert_allowed_url(url)
            seen.add(url)
            urls.append(url)
        return urls

    def normalize_listing_url(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed._replace(query="", fragment="").geturl().rstrip("/")

    def _anchor_count(self, page: Any) -> int:
        try:
            return int(page.locator("a[href]").count())
        except Exception:
            return 0

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
        price = self.extract_price(f"{title}\n{description}\n{text}")
        if not title or price is None:
            return None
        clean_description = description.strip() or text.strip()
        return Listing(
            marketplace=self.marketplace,
            external_id=self.external_id(page.url),
            title=title.strip()[:300],
            price=price,
            url=self.normalize_listing_url(page.url),
            description=clean_description[:2_000],
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
