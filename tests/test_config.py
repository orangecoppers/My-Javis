from copy import deepcopy

import pytest

from jarvis.config import validate_rules


def test_rules_are_valid(rules: dict) -> None:
    validate_rules(rules)


def test_total_limit_cannot_exceed_100(rules: dict) -> None:
    broken = deepcopy(rules)
    broken["collection"]["total_limit"] = 101
    with pytest.raises(ValueError, match="between 1 and 100"):
        validate_rules(broken)


def test_allocations_cannot_exceed_total(rules: dict) -> None:
    broken = deepcopy(rules)
    broken["collection"]["marketplaces"]["daangn"] = 16
    with pytest.raises(ValueError, match="allocations"):
        validate_rules(broken)

