import pytest

from jarvis.browser import LoggedInBunjangBrowser
from jarvis.safety import ApprovalService, DraftValidator, SafetyPolicy, SafetyViolation


class NullLogger:
    def emit(self, *args, **kwargs) -> None:
        pass


class FakeLocator:
    def __init__(self, exists: bool):
        self.exists = exists
        self.first = self
        self.value = ""

    def count(self) -> int:
        return int(self.exists)

    def fill(self, text: str) -> None:
        self.value = text


class FakePage:
    def __init__(self):
        self.textarea = FakeLocator(True)

    def locator(self, selector: str) -> FakeLocator:
        return self.textarea if selector == "textarea" else FakeLocator(False)


def test_external_navigation_is_blocked() -> None:
    policy = SafetyPolicy()
    policy.assert_allowed_url("https://m.bunjang.co.kr/products/123")
    with pytest.raises(SafetyViolation, match="blocked navigation"):
        policy.assert_allowed_url("https://example.com/products/123")


@pytest.mark.parametrize("action", ["send", "submit", "purchase", "pay", "checkout", "account_change"])
def test_high_impact_actions_are_blocked(action: str) -> None:
    with pytest.raises(SafetyViolation, match="blocked high-impact"):
        SafetyPolicy().assert_allowed_action(action)


def test_draft_filling_requires_matching_approval(tmp_path) -> None:
    approvals = ApprovalService()
    browser = LoggedInBunjangBrowser(tmp_path, SafetyPolicy(), approvals, NullLogger())
    page = FakePage()
    browser.fill_inquiry_page(page, "안녕하세요")
    assert page.textarea.value == "안녕하세요"
    with pytest.raises(SafetyViolation, match="fresh explicit approval"):
        approvals.consume("missing", "https://m.bunjang.co.kr/products/1", "안녕하세요")


def test_expired_approval_token_is_blocked() -> None:
    approvals = ApprovalService(ttl_seconds=-1)
    token = approvals.issue("https://m.bunjang.co.kr/products/1", "안녕하세요")
    with pytest.raises(SafetyViolation, match="expired"):
        approvals.consume(token.value, token.listing_url, token.draft_text)


def test_draft_validator_rejects_external_contact(rules: dict) -> None:
    validator = DraftValidator(rules)
    with pytest.raises(SafetyViolation, match="blocked phrase"):
        validator.validate("카카오톡 오픈채팅으로 연락 주세요")
