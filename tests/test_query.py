from jarvis.query import normalize_search_query


def test_normalize_removes_trailing_period() -> None:
    assert normalize_search_query("픽시.") == "픽시"


def test_normalize_removes_voice_command_words() -> None:
    assert normalize_search_query("자비스 엔진11 픽시 매물 찾아줘.") == "엔진11 픽시"


def test_normalize_keeps_brand_and_domain_terms() -> None:
    assert normalize_search_query("리더 픽시 검색해줘!!!") == "리더 픽시"


def test_normalize_defaults_empty_to_fixed_gear() -> None:
    assert normalize_search_query("...") == "픽시"


def test_normalize_rejects_unrelated_when_required() -> None:
    assert normalize_search_query("냉장고 포켓몬카드 찾아줘", require_fixed_gear_term=True) == ""
