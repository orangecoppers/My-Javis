from types import SimpleNamespace

import pytest

from jarvis.voice import LocalCommandParser, WakeWordListener, resolve_audio_device


class NullLogger:
    def emit(self, *args, **kwargs) -> None:
        pass


class FakeListener:
    def listen_phrase(self):
        return [1], 16_000


class FakeRecognizer:
    def transcribe(self, samples, sample_rate):
        return "자 비스 픽시 매물 찾아줘"


def test_parser_understands_search_command() -> None:
    command = LocalCommandParser().parse("자비스 리더 픽시 매물 찾아줘")
    assert command.name == "analyze_resale"
    assert command.arguments == {"query": "리더 픽시"}


def test_parser_discards_unrelated_search_terms() -> None:
    command = LocalCommandParser().parse("자비스 냉장고 포켓몬카드 리더 매물 찾아줘")
    assert command.name == "analyze_resale"
    assert command.arguments == {"query": "리더 픽시"}


def test_parser_rejects_search_without_fixed_gear_term() -> None:
    command = LocalCommandParser().parse("자비스 냉장고 포켓몬카드 찾아줘")
    assert command.name == "unsupported"


def test_parser_understands_ranked_draft_command() -> None:
    command = LocalCommandParser().parse("2번 후보 문의 초안 만들어줘")
    assert command.name == "create_inquiry_draft"
    assert command.arguments == {"rank": 2}


def test_parser_requires_pending_draft_for_approval() -> None:
    pending = {
        "listing_url": "https://m.bunjang.co.kr/products/1",
        "draft": "안녕하세요",
        "approval_token": "token",
    }
    command = LocalCommandParser().parse("응 입력해", pending)
    assert command.name == "confirm_and_fill_draft"
    assert command.arguments == {
        "listing_url": pending["listing_url"],
        "draft_text": pending["draft"],
        "approval_token": pending["approval_token"],
        "approved": True,
    }


def test_wakeword_accepts_transcribed_spacing() -> None:
    wakeword = WakeWordListener(FakeRecognizer(), FakeListener(), NullLogger())
    assert wakeword.wait() == "픽시 매물 찾아줘"


def test_audio_device_resolution_rejects_null_capture(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.voice.available_audio_devices", lambda: ["NULL Capture Device"])
    with pytest.raises(RuntimeError, match="실제 마이크"):
        resolve_audio_device(SimpleNamespace(audio_device_index=-1))


def test_audio_device_resolution_uses_explicit_device(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis.voice.available_audio_devices",
        lambda: ["MacBook Pro Microphone", "USB Microphone"],
    )
    assert resolve_audio_device(SimpleNamespace(audio_device_index=1)) == (1, "USB Microphone")
