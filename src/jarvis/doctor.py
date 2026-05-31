from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from jarvis.browser import chromium_installed, is_macos_intel, macos_microphone_permission_hint
from jarvis.config import Settings, load_rules
from jarvis.voice import available_audio_devices, has_real_audio_device


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_doctor(settings: Settings, console: Console | None = None) -> bool:
    console = console or Console()
    checks = [
        Check("macOS Intel", is_macos_intel(), f"{os.uname().sysname} {os.uname().machine}"),
        Check(
            "Playwright Chromium",
            chromium_installed(),
            "installed" if chromium_installed() else "run: playwright install chromium",
        ),
        Check("Rules YAML", _rules_valid(settings), str(settings.rules_path)),
        Check("faster-whisper", _module_exists("faster_whisper"), f"local model: {settings.whisper_model}"),
        Check(
            "Whisper model files",
            (settings.whisper_model_path / "model.bin").is_file(),
            str(settings.whisper_model_path),
        ),
        Check("pvrecorder", _module_exists("pvrecorder"), f"microphone: {macos_microphone_permission_hint()}"),
        Check("Microphone device", _real_audio_device_available(), _audio_device_detail()),
        Check("macOS say", shutil.which("say") is not None, "local text-to-speech"),
    ]
    table = Table(title="Javis doctor")
    table.add_column("상태")
    table.add_column("항목")
    table.add_column("설명")
    for check in checks:
        table.add_row("[green]OK[/green]" if check.ok else "[red]FAIL[/red]", check.name, check.detail)
    console.print(table)
    return all(check.ok for check in checks)


def _module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _rules_valid(settings: Settings) -> bool:
    try:
        load_rules(settings.rules_path)
    except Exception:
        return False
    return True


def _real_audio_device_available() -> bool:
    try:
        return has_real_audio_device()
    except Exception:
        return False


def _audio_device_detail() -> str:
    try:
        devices = available_audio_devices()
    except Exception as error:
        return f"device lookup failed: {error}"
    real_devices = [
        f"{index}: {name}"
        for index, name in enumerate(devices)
        if "NULL Capture Device" not in name
    ]
    return ", ".join(real_devices) if real_devices else "no real microphone; allow Terminal microphone access"
