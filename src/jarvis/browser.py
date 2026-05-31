from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from jarvis.events import EventLogger
from jarvis.safety import ApprovalService, SafetyPolicy, SafetyViolation


class PublicBrowser:
    def __init__(self, safety: SafetyPolicy, logger: EventLogger, headed: bool = True):
        self.safety = safety
        self.logger = logger
        self.headed = headed

    @contextmanager
    def page(self) -> Iterator[Any]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=not self.headed,
                env={},
                args=["--disable-extensions", "--disable-file-system"],
            )
            context = browser.new_context(accept_downloads=False, viewport={"width": 1280, "height": 720})
            page = context.new_page()
            context.on("page", lambda popup: popup.close() if popup != page else None)
            page.on("download", lambda download: download.cancel())
            try:
                yield page
            finally:
                context.close()
                browser.close()


class LoggedInBunjangBrowser:
    INPUT_SELECTORS = (
        "textarea[placeholder*='메시지']",
        "textarea[placeholder*='문의']",
        "textarea",
        "input[placeholder*='메시지']",
        "input[placeholder*='문의']",
    )

    def __init__(
        self,
        profile_path: Path,
        safety: SafetyPolicy,
        approvals: ApprovalService,
        logger: EventLogger,
    ):
        self.profile_path = profile_path
        self.safety = safety
        self.approvals = approvals
        self.logger = logger

    def login(self) -> None:
        from playwright.sync_api import sync_playwright

        self.profile_path.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(self.profile_path), headless=False, env={}
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://m.bunjang.co.kr/", wait_until="domcontentloaded")
            input("브라우저에서 직접 로그인한 뒤 Enter를 누르세요: ")
            context.close()

    def fill_inquiry(self, listing_url: str, draft_text: str, approval_token: str) -> None:
        from playwright.sync_api import sync_playwright

        self.safety.assert_bunjang_url(listing_url)
        self.approvals.consume(approval_token, listing_url, draft_text)
        self.profile_path.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(self.profile_path), headless=False, env={}
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(listing_url, wait_until="domcontentloaded")
            self.safety.assert_bunjang_url(page.url)
            self.fill_inquiry_page(page, draft_text)
            self.logger.emit("결과", "문의 초안을 입력칸에 채웠습니다. 전송은 직접 확인해 주세요.")
            input("브라우저 확인을 마쳤으면 Enter를 누르세요: ")
            context.close()

    def fill_inquiry_page(self, page: Any, draft_text: str) -> None:
        for selector in self.INPUT_SELECTORS:
            locator = page.locator(selector)
            if locator.count():
                locator.first.fill(draft_text)
                return
        raise SafetyViolation("문의 입력칸 selector를 찾지 못해 중단했습니다")


def chromium_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).exists()
    except Exception:
        return False


def macos_microphone_permission_hint() -> str:
    return "System Settings > Privacy & Security > Microphone"


def is_macos_intel() -> bool:
    return os.uname().sysname == "Darwin" and os.uname().machine == "x86_64"
