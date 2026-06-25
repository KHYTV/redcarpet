# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""일자별 기사 생성 (영상 제작 이전까지).

KST(Asia/Seoul) 기준 오늘/어제 발행분만 수집→필터→본문보강→기사작성→
팩트체크→검수→등급 까지 실행하고, 발행일별로 묶어 출력한다. Kling 영상은 제외.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import config
from collectors import reddit_collector, rss_collector, filter as item_filter
from processors import article_writer, fact_checker, article_reviewer, grader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("daily")

KST = timezone(timedelta(hours=9))
CAP_PER_DAY = 4  # 하루당 처리 상한 (비용·시간 제어)


def kst_date(item):
    """아이템의 발행 KST 날짜. published(ISO/RFC822) > collected_at 순."""
    for key in ("published", "collected_at"):
        val = item.get(key)
        if not val:
            continue
        try:
            dt = datetime.fromisoformat(val)
        except (ValueError, TypeError):
            try:
                dt = parsedate_to_datetime(val)
            except (ValueError, TypeError):
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).date()
    return None


def main():
    key = config.ANTHROPIC_API_KEY
    assert key, "ANTHROPIC_API_KEY 필요"

    now_kst = datetime.now(timezone.utc).astimezone(KST)
    today = now_kst.date()
    yesterday = today - timedelta(days=1)
    log.info("기준(KST): 오늘=%s, 어제=%s", today, yesterday)

    # 수집
    items = reddit_collector.collect_reddit(fetch_body=True, posts_per_sub=10)
    items += rss_collector.collect_rss()
    log.info("수집 합계: %d건", len(items))

    # 어제/오늘 발행분만
    target = {today, yesterday}
    dated = [x for x in items if kst_date(x) in target]
    log.info("어제/오늘 발행분: %d건", len(dated))

    # 필터(중복·점수·블랙리스트) 후 일자별 상한 적용
    filtered = item_filter.filter_items(dated)
    today_items = [x for x in filtered if kst_date(x) == today][:CAP_PER_DAY]
    yest_items = [x for x in filtered if kst_date(x) == yesterday][:CAP_PER_DAY]
    selected = today_items + yest_items
    log.info("처리 대상: 오늘 %d + 어제 %d = %d건",
             len(today_items), len(yest_items), len(selected))

    # 국내뉴스 본문 보강
    selected = rss_collector.enrich_korean_news(selected)

    # 기사화 → 팩트체크 → 검수 → 등급
    arts = article_writer.write_articles(selected, key)
    arts = [fact_checker.fact_check(a, key) for a in arts]
    arts = [article_reviewer.review_article(a, key) for a in arts]
    arts = grader.grade_all(arts)

    # 발행일 기준 그룹핑
    groups = {"오늘": [], "어제": []}
    for a in arts:
        d = kst_date(a)
        if d == today:
            groups["오늘"].append(a)
        elif d == yesterday:
            groups["어제"].append(a)

    json.dump({"today": str(today), "yesterday": str(yesterday), "articles": arts},
              open("output/results/_daily_articles.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 요약 출력
    print("\n" + "=" * 64)
    print(f"일자별 기사 (영상 제작 이전까지)  |  오늘={today}  어제={yesterday}")
    print("=" * 64)
    for label, group in (("어제", groups["어제"]), ("오늘", groups["오늘"])):
        print(f"\n■ {label} 작성 기사 ({len(group)}건)")
        for a in group:
            mark = "★발행" if a.get("action") == "publish" else " 보류" if a["grade"] == "B" else " 폐기"
            print(f"  [{a['grade']}/{a.get('score')}점·{mark}] {a.get('article_title','')[:42]}")
            print(f"        ↳ 출처 {a['source_type']} | 팩트 {'PASS' if a.get('fact_check_passed') else 'FAIL'}")


if __name__ == "__main__":
    main()
