from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

from jarvis.config import Settings
from jarvis.doctor import run_doctor
from jarvis.service import JarvisService
from jarvis.voice import (
    LocalSpeechRecognizer,
    OfflineVoiceSession,
    SpeechSegmentListener,
    WakeWordListener,
    audio_check,
    available_audio_devices,
    download_local_model,
    resolve_audio_device,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="Local fixed-gear resale voice assistant")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check local setup")
    commands.add_parser("download-model", help="download the local Whisper model once")
    commands.add_parser("audio-check", help="record four seconds and report microphone levels")
    commands.add_parser("speech-check", help="record one phrase and show local Whisper text")

    login = commands.add_parser("login", help="open a browser for manual login")
    login.add_argument("marketplace", choices=["bunjang"])

    commands.add_parser("run", help="wait for the local wake word and run offline voice commands")

    analyze = commands.add_parser("analyze", help="run one visible-browser research pass")
    analyze.add_argument("query", nargs="?", default="픽시")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load()
    if args.command == "doctor":
        return 0 if run_doctor(settings) else 1
    if args.command == "download-model":
        path = download_local_model(settings)
        print(f"로컬 Whisper 모델 저장 완료: {path}")
        return 0
    if args.command == "audio-check":
        _print_audio_devices()
        print("4초 동안 평소처럼 '자비스'라고 말해 주세요.", flush=True)
        try:
            result = audio_check(settings)
        except RuntimeError as error:
            print(f"마이크 확인 실패: {error}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["max_rms"] < result["threshold"]:
            print("음성 최대 RMS가 임계값보다 낮습니다. JARVIS_VOICE_ENERGY_THRESHOLD를 낮추세요.")
            return 1
        print("마이크 음량이 호출어 감지 임계값을 넘었습니다.")
        return 0
    if args.command == "speech-check":
        print("한 문장으로 '자비스 픽시 매물 찾아줘'라고 말해 주세요.", flush=True)
        listener = SpeechSegmentListener(settings)
        recognizer = LocalSpeechRecognizer(settings, _PrintLogger())
        samples, sample_rate = listener.listen_phrase(timeout_seconds=10)
        path = _save_speech_check(samples, sample_rate)
        print(f"녹음 저장: {path}")
        text = recognizer.transcribe(samples, sample_rate)
        print(f"로컬 Whisper 전사: {text or '<인식 실패>'}")
        return 0 if text else 1

    service = JarvisService(settings)
    if args.command == "login":
        service.logged_in_browser.login()
        return 0
    if args.command == "analyze":
        result = service.analyze_resale(args.query)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        return _run_voice_loop(settings, service)
    return 2


def _run_voice_loop(settings: Settings, service: JarvisService) -> int:
    try:
        _, device_name = resolve_audio_device(settings)
    except RuntimeError as error:
        print(f"마이크 확인 실패: {error}", file=sys.stderr)
        print("진단 명령: python -m jarvis audio-check", file=sys.stderr)
        return 1
    service.logger.emit("관찰", f"마이크 입력 장치: {device_name}")
    recognizer = LocalSpeechRecognizer(settings, service.logger)
    recognizer.prepare()
    OfflineVoiceSession.speak("자비스가 준비되었습니다.")
    listener = SpeechSegmentListener(settings)
    wakeword = WakeWordListener(recognizer, listener, service.logger)
    offline = OfflineVoiceSession(recognizer, listener, service.logger, service.dispatch_tool)
    while True:
        initial_text = wakeword.wait()
        try:
            offline.run(initial_text)
        except KeyboardInterrupt:
            raise
        except Exception as error:
            service.logger.emit("경고", f"오프라인 음성 처리 오류: {error}")
    return 0


def _print_audio_devices() -> None:
    print("입력 장치:")
    for index, name in enumerate(available_audio_devices()):
        print(f"  {index}: {name}")


class _PrintLogger:
    def emit(self, category: str, message: str, **details: object) -> None:
        print(f"[{category}] {message}")


def _save_speech_check(samples: list[int], sample_rate: int) -> Path:
    import numpy as np

    path = Path(".local/last-speech-check.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(np.asarray(samples, dtype=np.int16).tobytes())
    return path


if __name__ == "__main__":
    sys.exit(main())
