from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    rules_path: Path
    db_path: Path
    profile_path: Path
    whisper_model: str
    whisper_model_path: Path
    audio_device_index: int
    voice_energy_threshold: int

    @classmethod
    def load(cls, project_root: Path | None = None) -> "Settings":
        root = (project_root or PROJECT_ROOT).resolve()
        load_dotenv(root / ".env")

        def local_path(name: str, default: str) -> Path:
            value = os.getenv(name, default)
            path = Path(value).expanduser()
            return path if path.is_absolute() else root / path

        return cls(
            project_root=root,
            rules_path=local_path("JARVIS_RULES_PATH", "config/rules.yaml"),
            db_path=local_path("JARVIS_DB_PATH", ".local/jarvis.sqlite3"),
            profile_path=local_path("JARVIS_PROFILE_PATH", ".local/browser/bunjang-profile"),
            whisper_model=os.getenv("JARVIS_WHISPER_MODEL", "small"),
            whisper_model_path=local_path(
                "JARVIS_WHISPER_MODEL_PATH", ".local/models/faster-whisper-small"
            ),
            audio_device_index=int(os.getenv("JARVIS_AUDIO_DEVICE_INDEX", "-1")),
            voice_energy_threshold=int(os.getenv("JARVIS_VOICE_ENERGY_THRESHOLD", "450")),
        )


def load_rules(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        rules = yaml.safe_load(handle)
    if not isinstance(rules, dict):
        raise ValueError("rules YAML must contain a mapping")
    validate_rules(rules)
    return rules


def validate_rules(rules: dict[str, Any]) -> None:
    collection = rules.get("collection", {})
    total_limit = collection.get("total_limit")
    allocations = collection.get("marketplaces", {})
    if not isinstance(total_limit, int) or not 1 <= total_limit <= 100:
        raise ValueError("collection.total_limit must be between 1 and 100")
    if sum(allocations.values()) > total_limit:
        raise ValueError("marketplace allocations exceed collection.total_limit")
    delay = collection.get("detail_delay_seconds", [])
    if len(delay) != 2 or delay[0] < 1.5 or delay[1] < delay[0]:
        raise ValueError("detail delay must be an increasing range starting at 1.5 seconds")
