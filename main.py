"""RedCarpet 메인 파이프라인.

수집 → 필터 → 기사작성 → 팩트체크 → 검수/등급 → 숏폼 → 저장/발송 순으로 실행한다.
각 단계 실패는 로그에 남기고 다음 단계를 계속한다. cron으로 실행 가능.
"""

import logging
import os
from collections import Counter

import config


def _setup_logging() -> logging.Logger:
    os.makedirs(config.LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("redcarpet.main")


def run() -> dict:
    logger = _setup_logging()
    logger.info("=" * 60)
    logger.info("RedCarpet 파이프라인 시작")
    logger.info("=" * 60)

    # 지연 import: 일부 의존성 미설치 시에도 다른 단계 영향 최소화
    from collectors import reddit_collector, rss_collector, filter as item_filter
    from processors import article_writer, fact_checker, article_reviewer, grader
    from shortform import pipeline as shortform_pipeline
    from publishers import sheets_publisher, email_publisher

    summary = {"collected": 0, "filtered": 0, "articles": 0,
               "A": 0, "B": 0, "C": 0, "shortform_ok": 0}

    # ===== STEP 1~3: 수집 & 필터링 =====
    items = []
    try:
        logger.info("[STEP 1] Reddit 수집 시작")
        items += reddit_collector.collect_reddit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 1] Reddit 수집 실패: %s", exc)
    try:
        logger.info("[STEP 2] RSS 수집 시작")
        items += rss_collector.collect_rss()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 2] RSS 수집 실패: %s", exc)
    summary["collected"] = len(items)

    filtered = items
    try:
        logger.info("[STEP 3] 필터링 시작 (입력 %d건)", len(items))
        filtered = item_filter.filter_items(items)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 3] 필터링 실패: %s", exc)
    summary["filtered"] = len(filtered)

    # STEP 3.5: 국내 뉴스 본문 보강 (필터 통과분만 → 요청 최소화)
    try:
        logger.info("[STEP 3.5] 국내 뉴스 본문 보강")
        filtered = rss_collector.enrich_korean_news(filtered)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 3.5] 본문 보강 실패: %s", exc)

    # ===== STEP 4: 기사 작성 =====
    articles = []
    try:
        logger.info("[STEP 4] 기사 작성 시작 (%d건)", len(filtered))
        articles = article_writer.write_articles(filtered, config.ANTHROPIC_API_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 4] 기사 작성 실패: %s", exc)
    summary["articles"] = len(articles)

    # ===== STEP 5: 팩트체크 =====
    checked = []
    for article in articles:
        try:
            checked.append(fact_checker.fact_check(article, config.ANTHROPIC_API_KEY))
        except Exception as exc:  # noqa: BLE001
            logger.exception("[STEP 5] 팩트체크 실패: %s", exc)
            checked.append({**article, "fact_check_passed": True,
                            "fact_check_summary": f"오류: {exc}"})
    logger.info("[STEP 5] 팩트체크 완료 (%d건)", len(checked))

    # ===== STEP 6: 검수/교정 & 등급 =====
    reviewed = []
    for article in checked:
        try:
            reviewed.append(article_reviewer.review_article(article, config.ANTHROPIC_API_KEY))
        except Exception as exc:  # noqa: BLE001
            logger.exception("[STEP 6] 검수 실패: %s", exc)
            reviewed.append({**article, "score": 0})
    graded = []
    try:
        graded = grader.grade_all(reviewed)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 6] 등급 판정 실패: %s", exc)
        graded = reviewed
    grade_counts = Counter(a.get("grade") for a in graded)
    summary["A"] = grade_counts.get("A", 0)
    summary["B"] = grade_counts.get("B", 0)
    summary["C"] = grade_counts.get("C", 0)

    # ===== STEP 7: 숏폼 제작 (A등급만) =====
    shortform_results = []
    try:
        logger.info("[STEP 7] 숏폼 제작 시작")
        shortform_results = shortform_pipeline.run_shortform_pipeline(
            graded, config.ANTHROPIC_API_KEY,
            kling_api_key=config.KLING_API_KEY,
            kling_access_key=config.KLING_ACCESS_KEY,
            kling_secret_key=config.KLING_SECRET_KEY,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 7] 숏폼 제작 실패: %s", exc)
    summary["shortform_ok"] = sum(1 for r in shortform_results if r.get("status") == "completed")

    # ===== STEP 8: 저장 & 발송 =====
    try:
        logger.info("[STEP 8] Google Sheets 저장")
        sheets_publisher.save_articles(graded)
        sheets_publisher.save_shortform_results(shortform_results)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 8] Sheets 저장 실패: %s", exc)
    try:
        logger.info("[STEP 8] 뉴스레터 발송")
        email_publisher.send_newsletter(graded, config.NEWSLETTER_RECIPIENTS)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[STEP 8] 뉴스레터 발송 실패: %s", exc)

    # ===== 요약 =====
    logger.info("=" * 60)
    logger.info("파이프라인 완료 요약")
    logger.info("  수집: %d / 필터 후: %d / 기사: %d",
                summary["collected"], summary["filtered"], summary["articles"])
    logger.info("  등급 A=%d B=%d C=%d", summary["A"], summary["B"], summary["C"])
    logger.info("  숏폼 성공: %d", summary["shortform_ok"])
    logger.info("=" * 60)
    return summary


if __name__ == "__main__":
    run()
