# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""거부 기사 처리: 70점 기준 재적용 + 미달 기사 비판 재작성·재채점 (1회성)."""

import logging

import config
import db
from processors import deep_writer, ethics_reviewer
from processors.ethics_guidelines import ANIMAL_TYPES

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("rejected")

KEY_Q = {t["id"]: t["key_q"] for t in ANIMAL_TYPES}


def _split(body):
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
    arts = db.get_all()
    rewritten = promoted = 0
    for a in arts:
        score = a.get("ethics_score") or 0
        # 70점 이상이면 통과로 갱신(점수 변경 없이)
        if score >= config.ETHICS_PASS_MIN:
            if not a.get("ethics_passed"):
                a["ethics_passed"] = True
                db.upsert_article(a)
                promoted += 1
                log.info("기준완화 통과: %s (%d점)", a["title"][:30], score)
            continue

        # 미달 → 비판 기사로 재작성
        probe = {"article_title": a["title"], "article_body": "\n\n".join(a.get("paragraphs", []))}
        r0 = ethics_reviewer.ethics_review(probe, key)
        atype = r0.get("ethics_type", "companion")
        rw = deep_writer.critical_rewrite(
            probe, atype, KEY_Q.get(atype, ""), r0.get("ethics_violations", []), key)
        if not rw.get("body"):
            log.warning("재작성 실패, 원문 유지: %s", a["title"][:30])
            continue
        new_body = deep_writer.polish_body(rw["body"], key)
        r1 = ethics_reviewer.ethics_review(
            {"article_title": rw.get("title", a["title"]), "article_body": new_body}, key)

        a["title"] = rw.get("title", a["title"])
        a["lead"] = _lead(rw.get("summary", ""), new_body)
        a["paragraphs"] = _split(new_body)
        a["ethics_score"] = r1.get("ethics_score")
        a["ethics_passed"] = r1.get("ethics_passed")
        a["ethics_violations"] = r1.get("ethics_violations", [])
        db.upsert_article(a)
        rewritten += 1
        log.info("비판 재작성: %s → %s점 (%s)", a["title"][:28], a["ethics_score"],
                 "통과" if a["ethics_passed"] else "여전히 미달")

    print(f"\n완료: 기준완화 통과 {promoted}건, 비판 재작성 {rewritten}건")
    pub = sum(1 for x in db.get_all() if x.get("ethics_passed"))
    print(f"현재 게재 가능: {pub}/{db.count()}건")


if __name__ == "__main__":
    main()
