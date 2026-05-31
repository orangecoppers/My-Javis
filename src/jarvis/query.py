from __future__ import annotations

import re

PUNCTUATION_PATTERN = re.compile(r"[.,!?。！？\"'“”‘’()\[\]{}<>:;·…]+")
COMMAND_WORDS = (
    "자비스",
    "쟈비스",
    "jarvis",
    "찾아줘",
    "찾아",
    "검색해줘",
    "검색",
    "분석해줘",
    "분석",
    "매물",
    "후보",
    "좀",
    "해줘",
    "해주세요",
    "보여줘",
    "보여",
)
FIXED_GEAR_TERMS = (
    "픽시",
    "리더",
    "leader",
    "치넬리",
    "cinelli",
    "비고렐리",
    "vigorelli",
    "도스노벤타",
    "dosnoventa",
    "엔진11",
    "engine11",
    "언노운",
    "unknown",
    "코히즌",
    "cohesion",
    "아르마",
    "arma",
    "킹메이커",
    "kingmaker",
    "옴니움",
    "omnium",
    "듀라에이스",
    "dura ace",
    "카본",
    "프레임셋",
    "완차",
)


def normalize_search_query(text: str, *, require_fixed_gear_term: bool = False) -> str:
    """Normalize noisy CLI or Whisper text into a safe fixed-gear search query."""

    normalized = _basic_normalize(text)
    matched = _matched_fixed_gear_terms(normalized)
    if matched:
        return _fixed_gear_query(matched)
    if require_fixed_gear_term:
        return ""
    return normalized or "픽시"


def has_fixed_gear_term(text: str) -> bool:
    return bool(_matched_fixed_gear_terms(_basic_normalize(text)))


def _basic_normalize(text: str) -> str:
    normalized = text.lower()
    normalized = normalized.replace("엔진 11", "엔진11")
    normalized = normalized.replace("engine 11", "engine11")
    normalized = normalized.replace("dura-ace", "dura ace")
    normalized = PUNCTUATION_PATTERN.sub(" ", normalized)
    for word in COMMAND_WORDS:
        normalized = normalized.replace(word, " ")
    return " ".join(normalized.split())


def _matched_fixed_gear_terms(text: str) -> list[str]:
    compact = text.replace(" ", "")
    matched: list[str] = []
    for term in FIXED_GEAR_TERMS:
        needle = term.replace(" ", "")
        if needle in compact and term not in matched:
            matched.append(term)
    return matched


def _fixed_gear_query(terms: list[str]) -> str:
    cleaned = [term for term in terms if term != "픽시"]
    cleaned.append("픽시")
    return " ".join(dict.fromkeys(cleaned))
