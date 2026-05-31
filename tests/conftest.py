from pathlib import Path

import pytest

from jarvis.config import load_rules


@pytest.fixture
def rules() -> dict:
    return load_rules(Path("config/rules.yaml"))

