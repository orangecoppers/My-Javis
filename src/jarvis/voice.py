from __future__ import annotations

import math
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from jarvis.config import Settings
from jarvis.events import EventLogger
from jarvis.query import has_fixed_gear_term, normalize_search_query


DOMAIN_PROMPT = "자비스. 픽시 매물 찾아줘."
WAKE_WORD_PATTERN = re.compile(r"(?:자|쟈)\s*비스|jarvis", re.IGNORECASE)


def available_audio_devices() -> list[str]:
    from pvrecorder import PvRecorder

    return PvRecorder.get_available_devices()


def has_real_audio_device() -> bool:
    return any("NULL Capture Device" not in name for name in available_audio_devices())


def resolve_audio_device(settings: Settings) -> tuple[int, str]:
    devices = available_audio_devices()
    if not devices:
        raise RuntimeError("입력 장치를 찾지 못했습니다.")
    if settings.audio_device_index >= 0:
        if settings.audio_device_index >= len(devices):
            raise RuntimeError(
                f"JARVIS_AUDIO_DEVICE_INDEX={settings.audio_device_index} 장치가 없습니다."
            )
        return settings.audio_device_index, devices[settings.audio_device_index]
    for index, name in enumerate(devices):
        if "NULL Capture Device" not in name:
            return index, name
    raise RuntimeError(
        "실제 마이크를 찾지 못했습니다. macOS 설정에서 터미널의 마이크 권한을 허용한 뒤 "
        "터미널을 완전히 종료하고 다시 여세요."
    )


def audio_check(settings: Settings, seconds: float = 4.0) -> dict[str, Any]:
    from pvrecorder import PvRecorder

    device_index, device_name = resolve_audio_device(settings)
    recorder = PvRecorder(device_index=device_index, frame_length=512)
    recorder.start()
    energies: list[float] = []
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            energies.append(SpeechSegmentListener._energy(recorder.read()))
    finally:
        recorder.stop()
        recorder.delete()
    return {
        "device_index": device_index,
        "device_name": device_name,
        "threshold": settings.voice_energy_threshold,
        "average_rms": round(sum(energies) / max(1, len(energies)), 1),
        "max_rms": round(max(energies, default=0.0), 1),
    }


def download_local_model(settings: Settings) -> str:
    from huggingface_hub import snapshot_download

    settings.whisper_model_path.mkdir(parents=True, exist_ok=True)
    return snapshot_download(
        repo_id=f"Systran/faster-whisper-{settings.whisper_model}",
        local_dir=str(settings.whisper_model_path),
    )


@dataclass(frozen=True, slots=True)
class VoiceCommand:
    name: str
    arguments: dict[str, Any]


class LocalCommandParser:
    APPROVE_WORDS = ("승인", "입력해", "채워", "좋아", "응", "네", "예")
    REJECT_WORDS = ("취소", "거절", "하지 마", "아니", "됐어")

    def parse(self, text: str, pending_draft: dict[str, Any] | None = None) -> VoiceCommand:
        normalized = " ".join(text.lower().split())
        if pending_draft:
            if any(word in normalized for word in self.REJECT_WORDS):
                return VoiceCommand("cancel_task", {})
            if any(word in normalized for word in self.APPROVE_WORDS):
                return VoiceCommand(
                    "confirm_and_fill_draft",
                    {
                        "listing_url": pending_draft["listing_url"],
                        "draft_text": pending_draft["draft"],
                        "approval_token": pending_draft["approval_token"],
                        "approved": True,
                    },
                )

        if any(word in normalized for word in self.REJECT_WORDS):
            return VoiceCommand("cancel_task", {})
        if any(word in normalized for word in ("문의", "초안", "메시지")):
            rank = self._rank(normalized)
            if rank is not None:
                return VoiceCommand("create_inquiry_draft", {"rank": rank})
        if any(word in normalized for word in ("찾아", "검색", "분석")) and has_fixed_gear_term(normalized):
            query = normalize_search_query(normalized, require_fixed_gear_term=True)
            if query:
                return VoiceCommand("analyze_resale", {"query": query})
        return VoiceCommand("unsupported", {"text": text})

    @staticmethod
    def _rank(text: str) -> int | None:
        match = re.search(r"(\d+)\s*번", text)
        if match:
            return int(match.group(1))
        korean_numbers = {
            "일번": 1,
            "이번": 2,
            "삼번": 3,
            "사번": 4,
            "오번": 5,
            "육번": 6,
            "칠번": 7,
            "팔번": 8,
            "구번": 9,
            "십번": 10,
        }
        return next((rank for word, rank in korean_numbers.items() if word in text.replace(" ", "")), None)


class LocalSpeechRecognizer:
    def __init__(self, settings: Settings, logger: EventLogger):
        self.settings = settings
        self.logger = logger
        self._model: Any | None = None

    def transcribe(self, samples: list[int], sample_rate: int) -> str:
        if not samples:
            return ""
        import numpy as np

        model = self._load_model()
        audio = np.asarray(samples, dtype=np.float32) / 32768.0
        if sample_rate != 16_000:
            raise RuntimeError(f"local STT expects a 16 kHz microphone stream, got {sample_rate}")
        segments, _ = model.transcribe(
            audio,
            language="ko",
            beam_size=5,
            vad_filter=False,
            initial_prompt=DOMAIN_PROMPT,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def prepare(self) -> None:
        self._load_model()

    def _load_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            if not (self.settings.whisper_model_path / "model.bin").is_file():
                raise RuntimeError("local Whisper model is missing; run `python -m jarvis download-model`")
            self.logger.emit(
                "관찰",
                f"로컬 Whisper 모델을 불러옵니다: {self.settings.whisper_model_path}",
            )
            self._model = WhisperModel(
                str(self.settings.whisper_model_path),
                device="cpu",
                compute_type="int8",
            )
        return self._model


class SpeechSegmentListener:
    def __init__(
        self,
        settings: Settings,
        silence_seconds: float = 0.9,
        max_phrase_seconds: float = 8.0,
    ):
        self.settings = settings
        self.silence_seconds = silence_seconds
        self.max_phrase_seconds = max_phrase_seconds

    def listen_phrase(self, timeout_seconds: float | None = None) -> tuple[list[int], int]:
        from pvrecorder import PvRecorder

        device_index, _ = resolve_audio_device(self.settings)
        recorder = PvRecorder(device_index=device_index, frame_length=512)
        recorder.start()
        sample_rate = recorder.sample_rate
        pre_roll: deque[list[int]] = deque(maxlen=max(1, int(sample_rate * 0.4 / 512)))
        collected: list[int] = []
        speech_started = False
        silent_frames = 0
        started_at = time.monotonic()
        try:
            while True:
                if timeout_seconds and time.monotonic() - started_at >= timeout_seconds:
                    return collected, sample_rate
                frame = recorder.read()
                active = self._energy(frame) >= self.settings.voice_energy_threshold
                if not speech_started:
                    pre_roll.append(frame)
                    if not active:
                        continue
                    speech_started = True
                    for buffered in pre_roll:
                        collected.extend(buffered)
                    continue

                collected.extend(frame)
                silent_frames = 0 if active else silent_frames + 1
                if silent_frames * len(frame) / sample_rate >= self.silence_seconds:
                    return collected, sample_rate
                if len(collected) / sample_rate >= self.max_phrase_seconds:
                    return collected, sample_rate
        finally:
            recorder.stop()
            recorder.delete()

    @staticmethod
    def _energy(frame: list[int]) -> float:
        return math.sqrt(sum(sample * sample for sample in frame) / max(1, len(frame)))


class WakeWordListener:
    def __init__(
        self,
        recognizer: LocalSpeechRecognizer,
        listener: SpeechSegmentListener,
        logger: EventLogger,
    ):
        self.recognizer = recognizer
        self.listener = listener
        self.logger = logger

    def wait(self) -> str:
        self.logger.emit("관찰", "로컬 Whisper로 호출어 '자비스'를 기다립니다.")
        while True:
            samples, sample_rate = self.listener.listen_phrase()
            text = self.recognizer.transcribe(samples, sample_rate)
            if not WAKE_WORD_PATTERN.search(text):
                if text:
                    self.logger.emit("관찰", f"호출어 미일치: {text}")
                continue
            self.logger.emit("명령", f"호출어 감지: {text}")
            return WAKE_WORD_PATTERN.sub("", text, count=1).strip()


class OfflineVoiceSession:
    def __init__(
        self,
        recognizer: LocalSpeechRecognizer,
        listener: SpeechSegmentListener,
        logger: EventLogger,
        dispatch_tool: Any,
    ):
        self.recognizer = recognizer
        self.listener = listener
        self.logger = logger
        self.dispatch_tool = dispatch_tool
        self.parser = LocalCommandParser()
        self.pending_draft: dict[str, Any] | None = None

    def run(self, initial_text: str = "") -> None:
        text = initial_text or self._listen_after_prompt("네, 말씀하세요.")
        if not text:
            self.speak("명령을 듣지 못했습니다.")
            return
        self.logger.emit("명령", f"로컬 음성 명령: {text}")
        command = self.parser.parse(text, self.pending_draft)
        if command.name == "unsupported":
            self.speak("지원하는 명령은 매물 검색, 순위별 문의 초안, 승인, 취소입니다.")
            return
        if command.name == "analyze_resale" and not self._confirm_search(command.arguments["query"]):
            self.speak("검색을 취소했습니다.")
            return
        result = self.dispatch_tool(command.name, command.arguments)
        self._respond(command.name, result)

    def _confirm_search(self, query: str) -> bool:
        reply = self._listen_after_prompt(
            f"{query} 매물을 검색할까요? 실행하려면 검색 시작이라고 말해 주세요."
        )
        self.logger.emit("명령", f"검색 실행 확인 응답: {reply or '<없음>'}")
        return "검색 시작" in " ".join(reply.split())

    def _respond(self, name: str, result: dict[str, Any]) -> None:
        if name == "analyze_resale":
            count = int(result["count"])
            if count:
                top = result["items"][0]
                self.speak(f"분석을 마쳤습니다. 후보는 {count}개입니다. 1위는 {top['title']}입니다.")
            else:
                self.speak("수집된 번개장터 후보가 없습니다. 터미널 로그를 확인해 주세요.")
        elif name == "create_inquiry_draft":
            self.pending_draft = result
            reply = self._listen_after_prompt(f"문의 초안입니다. {result['draft']} 입력칸에 채울까요?")
            if reply:
                self.logger.emit("명령", f"문의 입력 확인 응답: {reply}")
                confirmation = self.parser.parse(reply, self.pending_draft)
                if confirmation.name in {"confirm_and_fill_draft", "cancel_task"}:
                    response = self.dispatch_tool(confirmation.name, confirmation.arguments)
                    self._respond(confirmation.name, response)
            else:
                self.speak("승인 응답을 듣지 못했습니다.")
        elif name == "confirm_and_fill_draft":
            self.pending_draft = None
            self.speak(result["message"])
        elif name == "cancel_task":
            self.pending_draft = None
            self.speak("취소했습니다.")

    def _listen_after_prompt(self, prompt: str) -> str:
        self.speak(prompt)
        samples, sample_rate = self.listener.listen_phrase(timeout_seconds=10)
        return self.recognizer.transcribe(samples, sample_rate)

    @staticmethod
    def speak(text: str) -> None:
        subprocess.run(["say", "-v", "Yuna", text], check=False)
