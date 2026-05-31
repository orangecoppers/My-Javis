import pytest

from jarvis.marketplaces.bunjang import BunjangAdapter
from jarvis.safety import SafetyPolicy, SafetyViolation


class RedirectingPage:
    url = ""

    def goto(self, url: str, wait_until: str) -> None:
        self.url = "https://example.com/tracker"


def test_adapter_blocks_redirect_to_external_host() -> None:
    adapter = BunjangAdapter(
        "https://m.bunjang.co.kr/search/products?q={query}",
        (1.5, 3.0),
        0,
        SafetyPolicy(),
    )
    with pytest.raises(SafetyViolation, match="blocked navigation"):
        adapter.collect(RedirectingPage(), "픽시", 1)
