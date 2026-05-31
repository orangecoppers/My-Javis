from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlparse


class SafetyViolation(RuntimeError):
    pass


class SafetyPolicy:
    ALLOWED_HOST_SUFFIXES = ("bunjang.co.kr", "joongna.com", "daangn.com")
    BLOCKED_ACTIONS = {"send", "submit", "purchase", "pay", "checkout", "account_change"}

    def assert_allowed_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise SafetyViolation("only HTTP(S) navigation is allowed")
        host = (parsed.hostname or "").lower()
        if not any(host == suffix or host.endswith(f".{suffix}") for suffix in self.ALLOWED_HOST_SUFFIXES):
            raise SafetyViolation(f"blocked navigation host: {host or '<missing>'}")

    def assert_allowed_action(self, action: str) -> None:
        if action.lower() in self.BLOCKED_ACTIONS:
            raise SafetyViolation(f"blocked high-impact action: {action}")

    def assert_bunjang_url(self, url: str) -> None:
        self.assert_allowed_url(url)
        host = (urlparse(url).hostname or "").lower()
        if not (host == "bunjang.co.kr" or host.endswith(".bunjang.co.kr")):
            raise SafetyViolation("draft filling is restricted to Bunjang")


@dataclass(frozen=True, slots=True)
class ApprovalToken:
    value: str
    listing_url: str
    draft_text: str
    expires_at: float


class ApprovalService:
    def __init__(self, ttl_seconds: int = 90):
        self.ttl_seconds = ttl_seconds
        self._tokens: dict[str, ApprovalToken] = {}

    def issue(self, listing_url: str, draft_text: str) -> ApprovalToken:
        token = ApprovalToken(
            value=secrets.token_urlsafe(24),
            listing_url=listing_url,
            draft_text=draft_text,
            expires_at=time.monotonic() + self.ttl_seconds,
        )
        self._tokens[token.value] = token
        return token

    def consume(self, token_value: str, listing_url: str, draft_text: str) -> ApprovalToken:
        token = self._tokens.pop(token_value, None)
        if token is None:
            raise SafetyViolation("draft filling requires a fresh explicit approval")
        if token.expires_at < time.monotonic():
            raise SafetyViolation("approval token expired")
        if token.listing_url != listing_url or token.draft_text != draft_text:
            raise SafetyViolation("approval token does not match this draft")
        return token


class DraftValidator:
    def __init__(self, rules: dict):
        self.max_length = int(rules["draft"]["max_length"])
        self.forbidden_phrases = [str(item).lower() for item in rules["draft"]["forbidden_phrases"]]

    def validate(self, text: str) -> str:
        normalized = " ".join(text.split())
        if not normalized:
            raise SafetyViolation("draft cannot be empty")
        if len(normalized) > self.max_length:
            raise SafetyViolation(f"draft exceeds {self.max_length} characters")
        lowered = normalized.lower()
        blocked = [phrase for phrase in self.forbidden_phrases if phrase in lowered]
        if blocked:
            raise SafetyViolation(f"draft contains blocked phrase: {blocked[0]}")
        return normalized
