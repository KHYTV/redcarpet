# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""기존 기사 → DB 마이그레이션 (1회성).

① 현재 output/results/_web_articles.json
② 직전 커밋(57194a3)의 web_sample.html에 임베드된 7건 심층 기사(ARTS)
를 복구해 DB에 누적 적재한다. source_key=제목 기준 중복 제거.
"""

import json
import re
import subprocess

import db

LABEL2CAT = {"반려견": "dog", "반려묘": "cat", "건강": "health",
             "훈련": "training", "반려동물 추모": "loss", "소식": "general"}
CAT_KW = {"dog": "dog", "cat": "cat", "health": "puppy",
          "training": "dog", "loss": "dog", "general": "pet"}
SRC2TYPE = {"레딧": "reddit", "국내뉴스": "korean_news"}


def from_current_json():
    try:
        arts = json.load(open("output/results/_web_articles.json", encoding="utf-8"))
    except Exception:
        return 0
    n = 0
    for a in arts:
        a = dict(a)
        a["source_key"] = a.get("source_key") or ("t:" + a.get("title", ""))
        db.upsert_article(a)
        n += 1
    return n


def from_git_html(commit="57194a3"):
    """커밋된 web_sample.html의 ARTS 배열에서 7건 복구."""
    try:
        html = subprocess.check_output(
            ["git", "show", f"{commit}:output/web_sample.html"],
            cwd=".", text=True, encoding="utf-8", stderr=subprocess.DEVNULL)
    except Exception as exc:
        print("git 복구 실패:", exc)
        return 0
    m = re.search(r"const ARTS = (\[.*?\]);\nconst ov", html, re.S)
    if not m:
        print("ARTS 미발견")
        return 0
    arts = json.loads(m.group(1))
    n = 0
    for a in arts:
        cat = LABEL2CAT.get(a.get("label", ""), "general")
        rec = {
            "source_key": "t:" + a.get("title", ""),
            "title": a.get("title", ""),
            "lead": a.get("lead", ""),
            "paragraphs": a.get("paragraphs", []),
            "category": cat,
            "photo_query": CAT_KW.get(cat, "pet"),
            "pub_date": a.get("date", ""),
            "source_type": SRC2TYPE.get(a.get("src", ""), ""),
            "grade": "A",  # 당시 게재됨
            "score": None,
            "ethics_score": a.get("ethics"),
            "ethics_passed": True,
            "ethics_violations": [],
            "deep_angles": a.get("angles", []),
            "is_deep": True,
        }
        db.upsert_article(rec)
        n += 1
    return n


if __name__ == "__main__":
    db.init_db()
    before = db.count()
    g = from_git_html()
    c = from_current_json()
    print(f"복구: git {g}건 + 현재 {c}건 | DB {before} → {db.count()}건")
    for a in db.get_all():
        print(f"  [{a['pub_date']}·{a['category']}·윤리{a['ethics_score']}] {a['title'][:38]}")
