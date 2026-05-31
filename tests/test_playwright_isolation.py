import importlib.util
from types import SimpleNamespace

import pytest

from jarvis.browser import LoggedInBunjangBrowser, PublicBrowser, chromium_installed
from jarvis.safety import SafetyPolicy


class NullLogger:
    def emit(self, *args, **kwargs) -> None:
        pass


@pytest.mark.skipif(
    importlib.util.find_spec("playwright") is None or not chromium_installed(),
    reason="Playwright Chromium is not installed",
)
def test_browser_contexts_keep_fixture_state_isolated() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        public_context = browser.new_context()
        login_context = browser.new_context()
        public_page = public_context.new_page()
        login_page = login_context.new_page()
        fixture = "data:text/html,<textarea></textarea>"
        public_page.goto(fixture)
        login_page.goto(fixture)
        helper = SimpleNamespace(INPUT_SELECTORS=LoggedInBunjangBrowser.INPUT_SELECTORS)
        LoggedInBunjangBrowser.fill_inquiry_page(helper, login_page, "초안")
        assert login_page.locator("textarea").input_value() == "초안"
        assert public_page.locator("textarea").input_value() == ""
        public_context.close()
        login_context.close()
        browser.close()


@pytest.mark.skipif(
    importlib.util.find_spec("playwright") is None or not chromium_installed(),
    reason="Playwright Chromium is not installed",
)
def test_public_browser_wrapper_launches_isolated_context() -> None:
    browser = PublicBrowser(SafetyPolicy(), NullLogger(), headed=False)
    with browser.page() as page:
        page.goto("data:text/html,<title>fixture</title>")
        assert page.title() == "fixture"
