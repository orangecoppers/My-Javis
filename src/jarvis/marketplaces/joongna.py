from __future__ import annotations

from urllib.parse import urlparse

from jarvis.marketplaces.base import MarketplaceAdapter


class JoongnaAdapter(MarketplaceAdapter):
    marketplace = "joongna"

    def is_listing_url(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        path = urlparse(url).path
        return host.endswith("joongna.com") and ("/product/" in path or "/articles/" in path)

