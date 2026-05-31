from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Listing:
    marketplace: str
    external_id: str
    title: str
    price: int
    url: str
    description: str = ""
    observed_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Analysis:
    listing: Listing
    score: float
    reference_median: int | None
    discount_ratio: float | None
    reference_count: int
    confidence: str
    reasons: list[str]


@dataclass(slots=True)
class Draft:
    listing_url: str
    text: str
    created_at: str = field(default_factory=utc_now)
    approved_at: str | None = None


@dataclass(slots=True)
class Event:
    category: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

