from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from jarvis.models import Event
from jarvis.storage import Storage


SENSITIVE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?<!\d)01[016789][ -]?\d{3,4}[ -]?\d{4}(?!\d)"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    result = value
    for pattern in SENSITIVE_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


class EventLogger:
    def __init__(self, storage: Storage, sink: Callable[[Event], None] | None = None):
        self.storage = storage
        self.sink = sink

    def emit(self, category: str, message: str, **details: Any) -> Event:
        event = Event(category=category, message=redact(message), details=redact(details))
        self.storage.save_event(event)
        if self.sink:
            self.sink(event)
        return event

