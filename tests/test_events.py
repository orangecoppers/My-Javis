import json
import sqlite3

from jarvis.events import EventLogger, redact
from jarvis.storage import Storage


def test_redact_removes_common_sensitive_values() -> None:
    value = redact(
        {
            "api_key": "sk-abcdefghijk",
            "phone": "010-1234-5678",
            "email": "person@example.com",
        }
    )
    assert value == {"api_key": "[REDACTED]", "phone": "[REDACTED]", "email": "[REDACTED]"}


def test_logger_persists_redacted_event(tmp_path) -> None:
    storage = Storage(tmp_path / "jarvis.sqlite3")
    storage.initialize()
    EventLogger(storage).emit("경고", "contact 010-1234-5678", email="person@example.com")
    with sqlite3.connect(storage.path) as connection:
        row = connection.execute("SELECT message, details_json FROM event_logs").fetchone()
    assert row[0] == "contact [REDACTED]"
    assert json.loads(row[1]) == {"email": "[REDACTED]"}

