from __future__ import annotations

from rich.console import Console
from rich.table import Table

from jarvis.models import Analysis, Event


CATEGORY_STYLES = {
    "명령": "bold cyan",
    "행동": "blue",
    "관찰": "white",
    "판단 요약": "magenta",
    "경고": "bold yellow",
    "결과": "bold green",
}


class RichMonitor:
    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def event(self, event: Event) -> None:
        style = CATEGORY_STYLES.get(event.category, "white")
        self.console.print(f"[{style}][{event.category}][/{style}] {event.message}")

    def shortlist(self, analyses: list[Analysis]) -> None:
        table = Table(title="번개장터 픽시 리셀 후보")
        table.add_column("#", justify="right")
        table.add_column("점수", justify="right")
        table.add_column("가격", justify="right")
        table.add_column("중앙값 대비", justify="right")
        table.add_column("표본", justify="right")
        table.add_column("신뢰도")
        table.add_column("상품")
        table.add_column("링크")
        for index, item in enumerate(analyses[:10], start=1):
            discount = "-" if item.discount_ratio is None else f"{item.discount_ratio:+.1%}"
            table.add_row(
                str(index),
                f"{item.score:.1f}",
                f"{item.listing.price:,}원",
                discount,
                str(item.reference_count),
                item.confidence,
                item.listing.title,
                item.listing.url,
            )
        self.console.print(table)

