from jarvis.analysis import ResaleAnalyzer, deduplicate_and_cap
from jarvis.models import Listing


def listing(marketplace: str, external_id: str, price: int, title: str = "픽시") -> Listing:
    return Listing(marketplace, external_id, title, price, f"https://example.com/{external_id}")


def test_deduplicate_and_cap() -> None:
    listings = [listing("bunjang", str(index), 100_000) for index in range(110)]
    listings.insert(2, listing("bunjang", "1", 200_000))
    assert len(deduplicate_and_cap(listings)) == 100
    assert [item.external_id for item in deduplicate_and_cap(listings, 3)] == ["0", "1", "2"]


def test_price_score_and_keyword_weight(rules: dict) -> None:
    analyzer = ResaleAnalyzer(rules)
    candidate = listing("bunjang", "candidate", 100_000, "리더 카본 픽시 상태좋음")
    references = [
        listing("joongna", "1", 200_000),
        listing("joongna", "2", 200_000),
        listing("daangn", "3", 200_000),
    ]
    result = analyzer.analyze([candidate], references)[0]
    assert result.score > 40
    assert result.discount_ratio > 0
    assert result.confidence == "보통"


def test_insufficient_samples_reduce_confidence(rules: dict) -> None:
    analyzer = ResaleAnalyzer(rules)
    result = analyzer.analyze([listing("bunjang", "candidate", 100_000)], [])[0]
    assert result.confidence == "낮음"
    assert "표본 부족" in result.reasons[-1]

