from __future__ import annotations

from typing import Any

from jarvis.analysis import ResaleAnalyzer, deduplicate_and_cap
from jarvis.browser import LoggedInBunjangBrowser, PublicBrowser
from jarvis.config import Settings, load_rules
from jarvis.drafts import DraftGenerator
from jarvis.events import EventLogger
from jarvis.marketplaces import BunjangAdapter, DaangnAdapter, JoongnaAdapter
from jarvis.models import Analysis, Draft, Listing
from jarvis.monitor import RichMonitor
from jarvis.safety import ApprovalService, SafetyPolicy
from jarvis.storage import Storage


class JarvisService:
    def __init__(self, settings: Settings, monitor: RichMonitor | None = None):
        self.settings = settings
        self.rules = load_rules(settings.rules_path)
        self.storage = Storage(settings.db_path)
        self.storage.initialize()
        self.monitor = monitor or RichMonitor()
        self.logger = EventLogger(self.storage, sink=self.monitor.event)
        self.safety = SafetyPolicy()
        self.approvals = ApprovalService()
        self.public_browser = PublicBrowser(self.safety, self.logger, headed=True)
        self.logged_in_browser = LoggedInBunjangBrowser(
            settings.profile_path, self.safety, self.approvals, self.logger
        )
        self.analyzer = ResaleAnalyzer(self.rules)
        self.draft_generator = DraftGenerator(self.rules)
        self._shortlist: list[Analysis] = []
        self._drafts: dict[str, Draft] = {}

    def analyze_resale(self, query: str = "픽시") -> dict[str, Any]:
        self.logger.emit("명령", f"리셀 분석 시작: {query}")
        run_id = self.storage.create_search_run(query)
        collection = self.rules["collection"]
        delay = tuple(float(value) for value in collection["detail_delay_seconds"])
        retry_limit = int(collection["retry_limit"])
        adapters = [
            BunjangAdapter(
                self.rules["marketplaces"]["bunjang"]["search_url"],
                delay,
                retry_limit,
                self.safety,
            ),
            JoongnaAdapter(
                self.rules["marketplaces"]["joongna"]["search_url"],
                delay,
                retry_limit,
                self.safety,
            ),
            DaangnAdapter(
                self.rules["marketplaces"]["daangn"]["search_url"],
                delay,
                retry_limit,
                self.safety,
            ),
        ]
        listings: list[Listing] = []
        with self.public_browser.page() as page:
            for adapter in adapters:
                limit = int(collection["marketplaces"][adapter.marketplace])
                self.logger.emit("행동", f"{adapter.marketplace} 공개 매물 탐색", limit=limit)
                found = adapter.collect(page, query, limit)
                self.logger.emit("관찰", f"{adapter.marketplace} 매물 {len(found)}개 수집")
                listings.extend(found)

        listings = deduplicate_and_cap(listings, int(collection["total_limit"]))
        listing_ids = {
            (listing.marketplace, listing.external_id): self.storage.save_listing(listing, run_id)
            for listing in listings
        }
        candidates = [listing for listing in listings if listing.marketplace == "bunjang"]
        references = [listing for listing in listings if listing.marketplace != "bunjang"]
        history = self.storage.previous_observed_prices(run_id)
        self._shortlist = self.analyzer.analyze(candidates, references, history)[:10]
        for item in self._shortlist:
            listing_id = listing_ids[(item.listing.marketplace, item.listing.external_id)]
            self.storage.save_analysis(listing_id, item)
        self.monitor.shortlist(self._shortlist)
        self.logger.emit("결과", f"번개장터 상위 후보 {len(self._shortlist)}개 분석 완료")
        return self.shortlist_summary()

    def shortlist_summary(self) -> dict[str, Any]:
        return {
            "count": len(self._shortlist),
            "items": [
                {
                    "rank": rank,
                    "title": item.listing.title,
                    "price": item.listing.price,
                    "score": item.score,
                    "confidence": item.confidence,
                    "url": item.listing.url,
                    "reasons": item.reasons[:4],
                }
                for rank, item in enumerate(self._shortlist, start=1)
            ],
        }

    def create_inquiry_draft(self, rank: int) -> dict[str, Any]:
        item = self._ranked_item(rank)
        draft = self.draft_generator.create(item.listing)
        self.storage.save_draft(draft)
        self._drafts[item.listing.url] = draft
        token = self.approvals.issue(draft.listing_url, draft.text)
        self.logger.emit("결과", f"{rank}번 후보 문의 초안을 만들었습니다.", draft=draft.text)
        return {
            "rank": rank,
            "listing_url": draft.listing_url,
            "draft": draft.text,
            "approval_token": token.value,
            "instruction": "초안을 읽고 사용자의 명시적인 음성 승인을 받은 뒤에만 입력하세요.",
        }

    def confirm_and_fill_draft(
        self, listing_url: str, draft_text: str, approval_token: str, approved: bool
    ) -> dict[str, str]:
        if not approved:
            self.logger.emit("경고", "사용자가 문의 초안 입력을 승인하지 않았습니다.")
            return {"status": "cancelled"}
        self.logged_in_browser.fill_inquiry(listing_url, draft_text, approval_token)
        return {"status": "filled", "message": "전송은 사용자가 브라우저에서 직접 해야 합니다."}

    def cancel_task(self) -> dict[str, str]:
        self.logger.emit("경고", "현재 작업을 취소했습니다.")
        return {"status": "cancelled"}

    def dispatch_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tools = {
            "analyze_resale": self.analyze_resale,
            "create_inquiry_draft": self.create_inquiry_draft,
            "confirm_and_fill_draft": self.confirm_and_fill_draft,
            "cancel_task": self.cancel_task,
        }
        if name not in tools:
            raise ValueError(f"unsupported local command: {name}")
        return tools[name](**arguments)

    def _ranked_item(self, rank: int) -> Analysis:
        if not 1 <= rank <= len(self._shortlist):
            raise ValueError(f"rank must be between 1 and {len(self._shortlist)}")
        return self._shortlist[rank - 1]
