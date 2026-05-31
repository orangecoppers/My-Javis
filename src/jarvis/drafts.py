from __future__ import annotations

from typing import Any

from jarvis.models import Draft, Listing
from jarvis.safety import DraftValidator


class DraftGenerator:
    def __init__(self, rules: dict[str, Any]):
        self.rules = rules
        self.validator = DraftValidator(rules)

    def create(self, listing: Listing) -> Draft:
        text = self._template_draft(listing)
        return Draft(listing_url=listing.url, text=self.validator.validate(text))

    def _template_draft(self, listing: Listing) -> str:
        return (
            f"안녕하세요. {listing.title[:45]} 아직 판매 중일까요? "
            "프레임 크랙이나 먹음 등 확인이 필요한 하자가 있는지, "
            "직거래 시 상태 확인이 가능한지 궁금합니다."
        )
