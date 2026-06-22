# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""수집 아이템 필터링.

1) 제목 Levenshtein 유사도 기반 중복 제거
2) Reddit 점수 하한 필터
3) 블랙리스트 키워드 필터
4) 최신순 MAX_ITEMS 컷
"""

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import Levenshtein

import config

logger = logging.getLogger(__name__)

BLACKLIST_KEYWORDS = ["광고", "sponsored", "advertisement", "AD"]
# 짧은 영문 약어("AD")는 부분문자열 매칭 시 road/head/ready 등에 오탐이 난다.
# 영문 키워드는 단어 경계로, 한글 키워드는 부분문자열로 매칭한다.
_LATIN_PATTERNS = [
    re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
    for kw in BLACKLIST_KEYWORDS
    if kw.isascii()
]
_NON_LATIN_KEYWORDS = [kw for kw in BLACKLIST_KEYWORDS if not kw.isascii()]


def _similarity(a: str, b: str) -> float:
    """두 문자열의 Levenshtein 비율 유사도(0~1)."""
    if not a and not b:
        return 1.0
    return Levenshtein.ratio(a.lower(), b.lower())


def _is_duplicate(title: str, kept_titles: list) -> bool:
    for existing in kept_titles:
        if _similarity(title, existing) >= config.DUPLICATE_THRESHOLD:
            return True
    return False


def _has_blacklist(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('content', '')}"
    if any(kw in text for kw in _NON_LATIN_KEYWORDS):
        return True
    return any(pat.search(text) for pat in _LATIN_PATTERNS)


_MIN_DT = datetime.min.replace(tzinfo=timezone.utc)


def _parse_dt(value: str):
    """RFC822(RSS) 또는 ISO8601(Reddit) 날짜 문자열을 tz-aware datetime으로 파싱."""
    if not value:
        return None
    # ISO8601 (예: 2026-06-20T10:00:00+00:00)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    # RFC822 (예: Wed, 31 Dec 2025 08:00:00 GMT)
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _sort_key(item: dict):
    """최신순 정렬용 키. 포맷이 다른 published/collected_at를 datetime으로 정규화해 비교.

    문자열 직접 비교 시 RFC822("Wed,...")가 ISO("2026-...")보다 항상 커서 소스가
    뒤섞이는 버그를 방지한다.
    """
    return (
        _parse_dt(item.get("published"))
        or _parse_dt(item.get("collected_at"))
        or _MIN_DT
    )


def filter_items(items: list) -> list:
    """필터 파이프라인을 적용해 최종 아이템 리스트를 반환한다."""
    # 최신 항목이 중복 비교에서 우선 살아남도록 먼저 최신순 정렬
    ordered = sorted(items, key=_sort_key, reverse=True)

    filtered = []
    kept_titles = []
    removed_score = removed_dup = removed_black = 0

    for item in ordered:
        # 2) Reddit 점수 하한
        if item.get("source_type") == "reddit":
            if item.get("score", 0) < config.MIN_REDDIT_SCORE:
                removed_score += 1
                continue

        # 3) 블랙리스트 키워드
        if _has_blacklist(item):
            removed_black += 1
            continue

        # 1) 중복 제거
        title = item.get("title", "")
        if _is_duplicate(title, kept_titles):
            removed_dup += 1
            continue

        filtered.append(item)
        kept_titles.append(title)

    # 4) 최신 MAX_ITEMS 컷 (이미 최신순이므로 앞에서 자른다)
    result = filtered[: config.MAX_ITEMS]

    logger.info(
        "필터링: 입력 %d → 출력 %d (점수제거 %d, 중복 %d, 블랙리스트 %d)",
        len(items), len(result), removed_score, removed_dup, removed_black,
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = [
        {"source_type": "reddit", "title": "강아지 산책", "content": "", "score": 50},
        {"source_type": "reddit", "title": "강아지 산책!", "content": "", "score": 30},
        {"source_type": "reddit", "title": "낮은 점수", "content": "", "score": 1},
        {"source_type": "korean_news", "title": "광고 포스트", "content": "sponsored"},
    ]
    print(filter_items(sample))
