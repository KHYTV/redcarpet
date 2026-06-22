# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""웹 샘플 기사를 2단계 심층 기사로 전면 교체.

_web_articles.json의 1차(씨앗) 기사들을 deep_pipeline으로 심층화하고,
웹 레이아웃 메타(category/pub_date/photo_query)는 보존한 채 심층 버전으로 덮어쓴다.
씨앗 기사는 게시하지 않는다(심층 버전만 게재).
"""

import json
import logging

import config
from collectors import rss_collector
from processors import deep_writer, fact_checker, article_reviewer, ethics_reviewer, grader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("deepen")


def _to_paragraphs(body: str) -> list:
    parts = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(parts) < 2:
        parts = [p.strip() for p in body.split("\n") if p.strip()]
    return parts


def _lead_from(summary: str, body: str) -> str:
    for line in (summary or "").splitlines():
        s = line.strip().lstrip("-•· ").strip()
        if s:
            return s
    return (body or "")[:80]


def main():
    key = config.ANTHROPIC_API_KEY
    web = json.load(open("output/results/_web_articles.json", encoding="utf-8"))
    log.info("씨앗 기사 %d건 → 심층화 시작", len(web))

    batch = rss_collector.collect_rss()  # 배치 교차참조용

    deepened = []
    for w in web:
        seed = {
            "article_title": w["title"],
            "article_body": "\n\n".join(w.get("paragraphs", [])),
            "title": w.get("title", ""),
            "url": w.get("url", ""),
            "source_type": w.get("source_type", ""),
        }
        try:
            related = deep_writer.find_related(seed, batch)
            deep = deep_writer.write_deep_article(seed, related, key)
        except Exception as exc:  # noqa: BLE001
            log.error("심층 작성 실패(%s): %s", w["title"][:25], exc)
            continue
        # 자체 팩트체크 → 검수 → 윤리 → 등급
        deep = fact_checker.fact_check(deep, key)
        deep = article_reviewer.review_article(deep, key)
        deep = ethics_reviewer.ethics_review(deep, key)
        deep = grader.grade_article(deep)

        # 웹 레이아웃용 엔트리 구성 (메타 보존)
        entry = {
            "title": deep["article_title"],
            "lead": _lead_from(deep.get("article_summary", ""), deep.get("article_body", "")),
            "paragraphs": _to_paragraphs(deep.get("article_body", "")),
            "category": w.get("category", "general"),
            "photo_query": w.get("photo_query", "pet"),
            "pub_date": w.get("pub_date", ""),
            "source_type": w.get("source_type", ""),
            "grade": deep.get("grade"),
            "score": deep.get("score"),
            "ethics_score": deep.get("ethics_score"),
            "ethics_passed": deep.get("ethics_passed"),
            "ethics_violations": deep.get("ethics_violations", []),
            "is_deep": True,
            "deep_angles": deep.get("deep_angles", []),
        }
        deepened.append(entry)
        log.info("심층화 완료: %s | 등급 %s/%s 윤리 %s (%d자, 각도 %d)",
                 entry["title"][:26], entry["grade"], entry["score"],
                 entry["ethics_score"], len("".join(entry["paragraphs"])), len(entry["deep_angles"]))

    json.dump(deepened, open("output/results/_web_articles.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    pub = [a for a in deepened if a.get("ethics_passed", True) and a.get("grade") in ("A", "B")]
    print(f"\n심층 기사 {len(deepened)}건 (게재가능 {len(pub)}건) 저장")


if __name__ == "__main__":
    main()
