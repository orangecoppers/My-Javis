from __future__ import annotations

import statistics
from collections.abc import Iterable
from typing import Any

from jarvis.models import Analysis, Listing


def deduplicate_and_cap(listings: Iterable[Listing], limit: int = 100) -> list[Listing]:
    if not 1 <= limit <= 100:
        raise ValueError("listing limit must be between 1 and 100")
    seen: set[tuple[str, str]] = set()
    result: list[Listing] = []
    for listing in listings:
        key = (listing.marketplace, listing.external_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(listing)
        if len(result) == limit:
            break
    return result


class ResaleAnalyzer:
    def __init__(self, rules: dict[str, Any]):
        self.rules = rules

    def analyze(
        self,
        candidates: list[Listing],
        references: list[Listing],
        historical_prices: list[int] | None = None,
    ) -> list[Analysis]:
        prices = [listing.price for listing in [*candidates, *references] if listing.price > 0]
        prices.extend(price for price in historical_prices or [] if price > 0)
        median = int(statistics.median(prices)) if prices else None
        sample_count = len(prices)
        return sorted(
            [self._analyze_listing(listing, median, sample_count) for listing in candidates],
            key=lambda item: item.score,
            reverse=True,
        )

    def _analyze_listing(
        self, listing: Listing, reference_median: int | None, sample_count: int
    ) -> Analysis:
        scoring = self.rules["scoring"]
        minimum_samples = int(scoring["minimum_reference_samples"])
        enough_samples = sample_count >= minimum_samples
        reasons: list[str] = []
        score = 0.0
        discount_ratio: float | None = None
        if reference_median and listing.price > 0:
            discount_ratio = (reference_median - listing.price) / reference_median
            price_score = max(-30.0, min(45.0, discount_ratio * 100.0))
            if not enough_samples:
                price_score *= float(scoring["insufficient_sample_price_multiplier"])
            score += price_score
            reasons.append(f"노출가 중앙값 대비 {discount_ratio:+.1%}")

        searchable_text = f"{listing.title} {listing.description}".lower()
        for group, keywords in scoring["keyword_weights"].items():
            for keyword, weight in keywords.items():
                if str(keyword).lower() in searchable_text:
                    score += float(weight)
                    reasons.append(f"{group}: {keyword} ({float(weight):+g})")

        if not enough_samples:
            reasons.append(f"표본 부족: {sample_count}/{minimum_samples}")
        return Analysis(
            listing=listing,
            score=round(score, 2),
            reference_median=reference_median,
            discount_ratio=discount_ratio,
            reference_count=sample_count,
            confidence="보통" if enough_samples else "낮음",
            reasons=reasons,
        )
