# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""실제 Reddit + 국내뉴스 본문보강 통합 end-to-end (Kling 제외).

Reddit 2건 + 국내뉴스 1건만 처리해 비용을 제한한다.
검증 포인트: ① Reddit 본문 수집 ② 국내뉴스 본문 보강 ③ 마커 제거된 깔끔한 본문.
"""

import logging

import config
from collectors import reddit_collector, rss_collector, filter as item_filter
from processors import article_writer, fact_checker, article_reviewer, grader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("verify_full")


def pick(items, source, n):
    return [x for x in items if x.get("source_type") == source][:n]


def main():
    key = config.ANTHROPIC_API_KEY
    assert key, "ANTHROPIC_API_KEY 필요"

    # 수집: Reddit 2개 서브레딧(본문 포함) + RSS
    reddit_items = []
    for sub in ["dogs", "dogtraining"]:
        reddit_items += reddit_collector._collect_one(sub, fetch_body=True, posts_per_sub=8)
    rss_items = rss_collector.collect_rss()
    log.info("수집: reddit=%d, rss=%d", len(reddit_items), len(rss_items))

    # 필터 → Reddit 2건 + 국내뉴스 1건 선별
    filtered = item_filter.filter_items(reddit_items + rss_items)
    sample = pick(filtered, "reddit", 2) + pick(filtered, "korean_news", 1)
    log.info("검증 샘플 %d건 선별", len(sample))

    # 국내뉴스 본문 보강 (실제 기사 스크래핑)
    sample = rss_collector.enrich_korean_news(sample)
    for s in sample:
        log.info("  [%s] %s | content %d자", s["source_type"], s["title"][:45], len(s.get("content", "")))

    # 기사화 → 팩트체크 → 검수 → 등급
    articles = article_writer.write_articles(sample, key)
    articles = [fact_checker.fact_check(a, key) for a in articles]
    articles = [article_reviewer.review_article(a, key) for a in articles]
    articles = grader.grade_all(articles)

    # 결과 출력
    print("\n" + "=" * 60)
    print("실제 Reddit + 국내뉴스 통합 end-to-end 결과")
    print("=" * 60)
    for a in articles:
        print(f"\n[{a['source_type']}] 등급 {a['grade']} / {a.get('score')}점")
        print("  원본:", a["title"][:55])
        print("  생성 제목:", a.get("article_title", ""))
        body = a.get("article_body", "")
        # 마커 잔존 검사
        has_marker = any(m in body for m in ["[기사 제목]", "[기사 본문]", "[편집자 주]", "[핵심요약]"])
        print("  본문 마커 잔존:", "있음(문제)" if has_marker else "없음(OK)")
        print("  본문 미리보기:", body[:160].replace("\n", " "))


if __name__ == "__main__":
    main()
