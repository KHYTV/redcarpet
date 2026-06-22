# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""2단계 심층 기사 오케스트레이터 (Stage 2).

1단계에서 추려진 A등급 씨앗 기사를 받아:
  심층 작성(deep_writer) → 자체 팩트체크(fact_checker) → 윤리 검증(ethics_reviewer)
  → 등급 재판정(grader) → publish 대상만 반환.
넓게 큐레이션한 1단계 위에, 가장 좋은 기사만 깊게 심층화하는 2단계.
"""

import logging

import config
from processors import deep_writer, fact_checker, article_reviewer, ethics_reviewer, grader

logger = logging.getLogger(__name__)


def run_deep_pipeline(graded_articles: list, all_items: list, api_key: str,
                      select_grade: str = "A") -> list:
    """1단계 결과 중 select_grade 기사를 심층화한다.

    all_items: 1단계에서 수집한 전체 아이템(배치 교차참조용).
    반환: 심층 기사 리스트(자체 팩트체크·윤리·등급 부착).
    """
    seeds = [a for a in graded_articles if a.get("grade") == select_grade]
    logger.info("[2단계] 심층화 대상: %d건 (등급 %s)", len(seeds), select_grade)

    deep_articles = []
    for seed in seeds:
        try:
            related = deep_writer.find_related(seed, all_items)
            deep = deep_writer.write_deep_article(seed, related, api_key)
        except Exception as exc:  # noqa: BLE001
            logger.error("심층 작성 실패: %s", exc)
            continue

        # 자체 팩트체크 → 검수/점수 → 윤리 → 등급 (기존 모듈 재사용)
        deep = fact_checker.fact_check(deep, api_key)
        deep = article_reviewer.review_article(deep, api_key)
        deep = ethics_reviewer.ethics_review(deep, api_key)
        deep = grader.grade_article(deep)
        deep_articles.append(deep)
        logger.info("[2단계] 심층 기사: %s → %s/%s (팩트 %s, 윤리 %s)",
                    deep.get("article_title", "")[:28], deep.get("grade"), deep.get("score"),
                    deep.get("fact_check_passed"), deep.get("ethics_score"))

    published = [a for a in deep_articles if a.get("action") == "publish"]
    logger.info("[2단계] 완료: 심층 %d건 중 발행 %d건", len(deep_articles), len(published))
    return deep_articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("deep_pipeline 로드 OK")
