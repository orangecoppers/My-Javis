from __future__ import annotations

from urllib.parse import urlparse

from jarvis.marketplaces.base import MarketplaceAdapter


class DaangnAdapter(MarketplaceAdapter):
    marketplace = "daangn"

    def is_listing_url(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        path = urlparse(url).path
        return host.endswith("daangn.com") and "/buy-sell/" in path

