# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""RedCar Pet 일일 웹사이트 빌드 (end-to-end).

수집 → 필터(오늘/어제 KST) → 본문보강 → 1차 기사(작성·팩트체크·검수·윤리·등급)
→ 교정/적합성 게이트 → 2차 심층화(자체 팩트체크·검수·윤리·등급)
→ _web_articles.json 저장 → build_html.py로 웹 샘플 재생성.

매일 오전 9시(KST) Windows 작업 스케줄러로 실행되도록 설계.
환경변수 DAILY_CAP 으로 일일 처리 상한 조절(기본 5).
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import anthropic

import config
import db
from collectors import reddit_collector, rss_collector, filter as item_filter
from processors import (article_writer, fact_checker, article_reviewer,
                        ethics_reviewer, grader, deep_writer)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("build_site")

KST = timezone(timedelta(hours=9))
CAP = int(os.environ.get("DAILY_CAP", "5"))

COPYEDIT_PROMPT = """다음 반려동물 기사가 웹 매거진 게시에 적합한지 판정하고 메타데이터를 부여해줘.
밈·자랑·잡담·정보없는 글이면 suitable=false.

반드시 JSON으로만:
{{"suitable": true, "title": "자연스러운 한국어 제목", "category": "dog|cat|health|training|loss|general",
  "photo_query": "english stock photo query"}}

[제목] {title}
[본문] {body}
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


def _paras(body):
    parts = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(parts) < 2:
        parts = [p.strip() for p in body.split("\n") if p.strip()]
    return parts


def _lead(summary, body):
    for line in (summary or "").splitlines():
        s = line.strip().lstrip("-•· ").strip()
        if s:
            return s
    return (body or "")[:80]


def main():
    key = config.ANTHROPIC_API_KEY
    if not key:
        log.error("ANTHROPIC_API_KEY 없음 - 중단")
        return
    now = datetime.now(timezone.utc).astimezone(KST)
    today, yest = now.date(), now.date() - timedelta(days=1)
    log.info("=== RedCar Pet 일일 빌드 (KST %s) | 대상 %s~%s | CAP=%d ===",
             now.strftime("%Y-%m-%d %H:%M"), yest, today, CAP)

    # 1. 수집
    items = reddit_collector.collect_reddit(fetch_body=True, posts_per_sub=10)
    items += rss_collector.collect_rss()
    log.info("수집 %d건", len(items))

    # 2. 오늘/어제 발행분 필터 + 상한
    recent = [x for x in items if kst_date(x) in {today, yest}]
    seeds = item_filter.filter_items(recent)[:CAP]
    seeds = rss_collector.enrich_korean_news(seeds)
    log.info("씨앗 후보 %d건", len(seeds))

    # 3. 1차 기사 체인
    arts = article_writer.write_articles(seeds, key)
    arts = [fact_checker.fact_check(a, key) for a in arts]
    arts = [article_reviewer.review_article(a, key) for a in arts]
    arts = [ethics_reviewer.ethics_review(a, key) for a in arts]
    arts = grader.grade_all(arts)
    for a in arts:
        a["pub_date"] = str(kst_date(a))

    # 4. 윤리 통과 + 적합성/교정 게이트
    client = anthropic.Anthropic(api_key=key)
    candidates = []
    for a in arts:
        if a.get("ethics_passed") is False:
            log.info("1차 윤리 거부 제외: %s", a.get("article_title", "")[:30])
            continue
        try:
            resp = client.messages.create(
                model=config.MODEL_REVIEWER, max_tokens=600,
                messages=[{"role": "user", "content": COPYEDIT_PROMPT.format(
                    title=a.get("article_title", ""), body=a.get("article_body", "")[:2500])}],
            )
            ce = _extract_json(resp.content[0].text)
        except Exception as exc:  # noqa: BLE001
            log.warning("적합성 판정 실패: %s", exc)
            continue
        if not ce.get("suitable"):
            log.info("부적합 제외: %s", a.get("article_title", "")[:30])
            continue
        candidates.append({
            "article_title": ce.get("title", a.get("article_title", "")),
            "article_body": a.get("article_body", ""),
            "title": a.get("article_title", ""),
            "url": a.get("url", ""),
            # 원본 식별자: URL 우선, 없으면 원제목 → 재실행 시 중복 방지 키
            "source_key": a.get("url") or ("t:" + a.get("article_title", "")),
            "source_type": a.get("source_type", ""),
            "category": ce.get("category", "general"),
            "photo_query": ce.get("photo_query", "pet"),
            "pub_date": a.get("pub_date", ""),
        })
    log.info("심층화 대상 %d건", len(candidates))

    # 5. 2차 심층화 (자체 팩트체크·검수·윤리·등급)
    web = []
    for seed in candidates:
        try:
            related = deep_writer.find_related(seed, items)
            deep = deep_writer.write_deep_article(seed, related, key)
        except Exception as exc:  # noqa: BLE001
            log.error("심층 작성 실패: %s", exc)
            continue
        deep = fact_checker.fact_check(deep, key)
        deep = article_reviewer.review_article(deep, key)
        deep = ethics_reviewer.ethics_review(deep, key)
        deep = grader.grade_article(deep)
        entry = {
            "source_key": seed["source_key"],
            "title": deep["article_title"],
            "lead": _lead(deep.get("article_summary", ""), deep.get("article_body", "")),
            "paragraphs": _paras(deep.get("article_body", "")),
            "category": seed["category"], "photo_query": seed["photo_query"],
            "pub_date": seed["pub_date"], "source_type": seed["source_type"],
            "grade": deep.get("grade"), "score": deep.get("score"),
            "ethics_score": deep.get("ethics_score"), "ethics_passed": deep.get("ethics_passed"),
            "ethics_violations": deep.get("ethics_violations", []),
            "is_deep": True, "deep_angles": deep.get("deep_angles", []),
            "image_keywords": deep_writer.image_keywords(deep, key),  # 단락 매칭 이미지 키워드
        }
        web.append(entry)
        db.upsert_article(entry)  # DB에 누적 보관(중복은 source_key로 갱신)
        log.info("심층 완료·DB저장: %s (등급 %s, 윤리 %s)",
                 deep["article_title"][:28], deep.get("grade"), deep.get("ethics_score"))

    os.makedirs(os.path.join(config.RESULTS_DIR), exist_ok=True)
    out = os.path.join(config.RESULTS_DIR, "_web_articles.json")
    json.dump(web, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log.info("이번 빌드 심층 %d건 저장 → %s | DB 누적 %d건", len(web), out, db.count())

    # 6. HTML 재생성 (DB에 누적된 전체 기사로 — 오늘 신규 0건이어도 기존분 게재)
    if db.count() > 0:
        subprocess.run([sys.executable, "build_html.py"], cwd=config.BASE_DIR, check=True)
        log.info("웹 샘플 재생성 완료 (DB 누적 %d건)", db.count())
    else:
        log.warning("DB에 기사 0건 — HTML 재생성 건너뜀")

    # 7. 정적 호스팅 자동 배포 (DEPLOY_TARGET 설정 시)
    if config.DEPLOY_TARGET and db.count() > 0:
        try:
            import deploy_static
            deploy_static.deploy()
        except Exception as exc:  # noqa: BLE001
            log.exception("[STEP 7] 자동 배포 실패: %s", exc)

    log.info("=== 일일 빌드 종료: 이번 신규 %d건 / DB 총 %d건 ===", len(web), db.count())


if __name__ == "__main__":
    main()
