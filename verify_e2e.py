"""Kling 직전 단계까지 실제 데이터 end-to-end 검증.

수집 → 필터 → 기사작성 → 팩트체크 → 검수/등급 → (A등급) 숏폼 대본 생성.
비용 절감을 위해 LIMIT건만 처리한다. Kling 영상 생성/자막 합성은 제외.
"""

import logging

import config
from collectors import reddit_collector, rss_collector, filter as item_filter
from processors import article_writer, fact_checker, article_reviewer, grader
from shortform import script_generator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("verify")

LIMIT = 2  # 처리할 아이템 수 (비용 절감)


def main():
    key = config.ANTHROPIC_API_KEY
    assert key, "ANTHROPIC_API_KEY 필요"

    # STEP 1~3: 수집 & 필터
    items = reddit_collector.collect_reddit() + rss_collector.collect_rss()
    log.info("[1-2] 수집: %d건", len(items))
    filtered = item_filter.filter_items(items)[:LIMIT]
    log.info("[3] 필터 후 %d건만 검증에 사용", len(filtered))
    for i, it in enumerate(filtered):
        log.info("   %d. [%s] %s", i + 1, it["source_type"], it["title"][:50])

    # STEP 4: 기사 작성
    articles = article_writer.write_articles(filtered, key)
    log.info("[4] 기사 작성: %d건", len(articles))

    # STEP 5: 팩트체크
    checked = [fact_checker.fact_check(a, key) for a in articles]
    log.info("[5] 팩트체크: passed=%s", [c.get("fact_check_passed") for c in checked])

    # STEP 6: 검수 + 등급
    reviewed = [article_reviewer.review_article(a, key) for a in checked]
    graded = grader.grade_all(reviewed)
    log.info("[6] 등급: %s", [(g.get("score"), g.get("grade"), g.get("action")) for g in graded])

    # STEP 7(전단계): A등급 기사 → 숏폼 대본 생성 (Kling 영상 생성은 제외)
    a_articles = [g for g in graded if g.get("grade") == "A"]
    log.info("[7-pre] A등급 %d건 → 숏폼 대본 생성", len(a_articles))
    scripts = []
    for a in a_articles:
        try:
            s = script_generator.generate_script(a, key)
            scripts.append((a, s))
            log.info("   대본 OK: %d장면 / %s초 / hook=%s",
                     len(s.get("scenes", [])), s.get("total_duration"), s.get("hook", "")[:30])
        except Exception as exc:  # noqa: BLE001
            log.error("   대본 실패: %s", exc)

    # 최종 요약
    print("\n" + "=" * 55)
    print("Kling 직전까지 end-to-end 검증 결과")
    print("=" * 55)
    print(f"  수집: {len(items)} → 필터/샘플: {len(filtered)}")
    print(f"  기사 작성: {len(articles)}")
    print(f"  팩트체크 통과: {sum(1 for c in checked if c.get('fact_check_passed'))}/{len(checked)}")
    g = grader  # 등급 분포
    from collections import Counter
    dist = Counter(x.get("grade") for x in graded)
    print(f"  등급: A={dist.get('A',0)} B={dist.get('B',0)} C={dist.get('C',0)}")
    print(f"  숏폼 대본 생성 성공: {len(scripts)}/{len(a_articles)} (A등급 대상)")
    print("=" * 55)

    # 첫 A등급 기사 + 대본 상세 1건 미리보기
    if scripts:
        a, s = scripts[0]
        print("\n[샘플] 기사 제목:", a.get("article_title"))
        print("[샘플] 등급/점수:", a.get("grade"), "/", a.get("score"))
        print("[샘플] 대본 hook:", s.get("hook"))
        print("[샘플] 플랫폼별 제목:", s.get("title_per_platform"))


if __name__ == "__main__":
    main()
