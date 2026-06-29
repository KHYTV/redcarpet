# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""기존 DB 기사를 5유형 윤리 준칙으로 재채점 (1회성)."""

import logging

import config
import db
from processors import ethics_reviewer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    key = config.ANTHROPIC_API_KEY
    arts = db.get_all()
    rejected = 0
    for a in arts:
        probe = {"article_title": a["title"], "article_body": "\n\n".join(a.get("paragraphs", []))}
        r = ethics_reviewer.ethics_review(probe, key)
        a["ethics_score"] = r.get("ethics_score")
        a["ethics_passed"] = r.get("ethics_passed")
        a["ethics_violations"] = r.get("ethics_violations", [])
        db.upsert_article(a)
        if not a["ethics_passed"]:
            rejected += 1
        print(f"  [{r.get('ethics_type')}·{a['ethics_score']}점·{'통과' if a['ethics_passed'] else '거부'}] {a['title'][:32]}")
    print(f"\n재채점 완료: {len(arts)}건 (거부 {rejected}건)")


if __name__ == "__main__":
    main()
