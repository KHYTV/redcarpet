# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""웹 게시 샘플용 기사 준비.

그제(06-21)분 신규 생성 + 어제(06-22)분 재사용 → 교정교열/적합성 판정 패스 →
웹 게시용 데이터(_web_articles.json) 저장. 부적합(밈/자랑/잡담)은 제외.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import anthropic

import config
from collectors import reddit_collector, rss_collector, filter as item_filter
from processors import article_writer, fact_checker, article_reviewer, grader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("web")

KST = timezone(timedelta(hours=9))

COPYEDIT_PROMPT = """다음 반려동물 기사를 웹 매거진 게시용으로 교정·교열해줘.

작업:
1) 적합성 판정: 정보성/공감형 기사로 적합한가? 단순 밈·자랑·잡담·정보없는 글이면 suitable=false.
2) 제목을 자연스러운 한국어로 (영어면 번역). 클릭하고 싶은 깔끔한 제목.
3) 본문 맞춤법·문장·흐름 교정. 웹 가독성 위해 2~4개 단락으로 정리.
4) 카테고리 분류: dog | cat | health | training | loss | general
5) 어울리는 사진 검색어(영어 stock photo query) 1개.

반드시 아래 JSON으로만 응답:
{{
  "suitable": true,
  "reason": "판정 이유",
  "title": "교정된 한국어 제목",
  "lead": "한 문장 리드(요약)",
  "paragraphs": ["단락1", "단락2", "단락3"],
  "category": "dog",
  "photo_query": "golden retriever walking in park"
}}

[현재 제목]
{title}

[본문]
{body}
"""


def kst_date(item):
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


def _extract_json(text):
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1])


def generate_for_date(target_date, key, cap=4):
    items = reddit_collector.collect_reddit(fetch_body=True, posts_per_sub=10)
    items += rss_collector.collect_rss()
    dated = [x for x in items if kst_date(x) == target_date]
    filtered = item_filter.filter_items(dated)[:cap]
    filtered = rss_collector.enrich_korean_news(filtered)
    arts = article_writer.write_articles(filtered, key)
    arts = [fact_checker.fact_check(a, key) for a in arts]
    arts = [article_reviewer.review_article(a, key) for a in arts]
    arts = grader.grade_all(arts)
    for a in arts:
        a["pub_date"] = str(kst_date(a))
    return arts


def copyedit(article, client):
    prompt = COPYEDIT_PROMPT.format(
        title=article.get("article_title", ""),
        body=article.get("article_body", "")[:4000],
    )
    resp = client.messages.create(
        model=config.MODEL_REVIEWER, max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _extract_json(resp.content[0].text)
    data["pub_date"] = article.get("pub_date", "")
    data["source_type"] = article.get("source_type", "")
    data["grade"] = article.get("grade", "")
    data["score"] = article.get("score", 0)
    return data


def main():
    key = config.ANTHROPIC_API_KEY
    now_kst = datetime.now(timezone.utc).astimezone(KST)
    yesterday = now_kst.date() - timedelta(days=1)      # 어제
    day_before = now_kst.date() - timedelta(days=2)     # 그제
    log.info("어제=%s, 그제=%s", yesterday, day_before)

    # 어제(06-22) 재사용
    try:
        saved = json.load(open("output/results/_daily_articles.json", encoding="utf-8"))
        y_articles = [a for a in saved["articles"] if kst_date(a) == yesterday]
        for a in y_articles:
            a["pub_date"] = str(yesterday)
        log.info("어제분 재사용: %d건", len(y_articles))
    except Exception:
        y_articles = generate_for_date(yesterday, key)

    # 그제(06-21) 신규 생성
    log.info("그제분 신규 생성...")
    d_articles = generate_for_date(day_before, key)
    log.info("그제분: %d건", len(d_articles))

    # 교정교열 + 적합성 판정
    client = anthropic.Anthropic(api_key=key)
    web = []
    for a in y_articles + d_articles:
        try:
            ce = copyedit(a, client)
            status = "적합" if ce.get("suitable") else "부적합(" + ce.get("reason", "")[:20] + ")"
            log.info("교정 [%s] %s -> %s", ce.get("pub_date"), a.get("article_title", "")[:30], status)
            if ce.get("suitable"):
                web.append(ce)
        except Exception as exc:  # noqa: BLE001
            log.warning("교정 실패: %s", exc)

    json.dump(web, open("output/results/_web_articles.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n웹 게시 적합 기사: {len(web)}건 저장")
    for w in web:
        print(f"  [{w['pub_date']}·{w['category']}] {w['title']}")


if __name__ == "__main__":
    main()
