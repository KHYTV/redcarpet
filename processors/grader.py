# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""등급 판정.

score 기준으로 A/B/C 등급과 후속 action을 결정한다.
fact_check_passed=False면 강제로 C 등급(discard)으로 떨어뜨린다.
"""

import logging
from collections import Counter

import config

logger = logging.getLogger(__name__)


def grade_article(article: dict) -> dict:
    """단일 기사에 grade/action 필드를 부착해 반환한다."""
    result = dict(article)
    score = result.get("score", 0) or 0

    # 팩트체크 또는 윤리검증 탈락 시 강제 C (두 거부권)
    if result.get("fact_check_passed") is False:
        grade, action = "C", "discard"
        result["grade_reason"] = "fact_check_failed"
    elif result.get("ethics_passed") is False:
        grade, action = "C", "discard"
        result["grade_reason"] = "ethics_violation"
    elif score >= config.GRADE_A_MIN:
        grade, action = "A", "publish"
    elif score >= config.GRADE_B_MIN:
        grade, action = "B", "hold"
    else:
        grade, action = "C", "discard"

    result["grade"] = grade
    result["action"] = action
    return result


def grade_all(articles: list) -> list:
    """전체 기사에 등급을 매기고 통계를 로그로 출력한다."""
    graded = [grade_article(a) for a in articles]
    stats = Counter(a["grade"] for a in graded)
    logger.info(
        "등급 통계: A=%d, B=%d, C=%d (총 %d)",
        stats.get("A", 0), stats.get("B", 0), stats.get("C", 0), len(graded),
    )
    return graded


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    samples = [
        {"score": 82, "fact_check_passed": True},
        {"score": 60, "fact_check_passed": True},
        {"score": 90, "fact_check_passed": False},
        {"score": 30, "fact_check_passed": True},
    ]
    for g in grade_all(samples):
        print(g["score"], g["grade"], g["action"])
