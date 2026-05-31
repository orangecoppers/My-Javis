from __future__ import annotations

from urllib.parse import urlparse

from jarvis.marketplaces.base import MarketplaceAdapter


class BunjangAdapter(MarketplaceAdapter):
    marketplace = "bunjang"

    def is_listing_url(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host.endswith("bunjang.co.kr") and "/products/" in urlparse(url).path

