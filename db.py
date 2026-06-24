# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""기사 아카이브 DB (SQLite).

전체 기사를 output/redcarpet.db에 누적 보관한다. source_key(원본 식별자)로
UPSERT하여 재실행 시 중복을 방지하고, 웹 빌더는 DB에서 읽어 누적 게재한다.
"""

import json
import os
import sqlite3

import config

DB_PATH = os.path.join(config.OUTPUT_DIR, "redcarpet.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  source_key   TEXT PRIMARY KEY,
  title        TEXT,
  lead         TEXT,
  paragraphs   TEXT,
  category     TEXT,
  photo_query  TEXT,
  pub_date     TEXT,
  source_type  TEXT,
  grade        TEXT,
  score        INTEGER,
  ethics_score INTEGER,
  ethics_passed INTEGER,
  ethics_violations TEXT,
  deep_angles  TEXT,
  is_deep      INTEGER,
  created_at   TEXT DEFAULT (datetime('now')),
  updated_at   TEXT DEFAULT (datetime('now'))
);
"""


def _conn():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.executescript(SCHEMA)


def _row(a):
    return {
        "source_key": a["source_key"],
        "title": a.get("title", ""),
        "lead": a.get("lead", ""),
        "paragraphs": json.dumps(a.get("paragraphs", []), ensure_ascii=False),
        "category": a.get("category", "general"),
        "photo_query": a.get("photo_query", "pet"),
        "pub_date": a.get("pub_date", ""),
        "source_type": a.get("source_type", ""),
        "grade": a.get("grade"),
        "score": a.get("score"),
        "ethics_score": a.get("ethics_score"),
        "ethics_passed": 1 if a.get("ethics_passed", True) else 0,
        "ethics_violations": json.dumps(a.get("ethics_violations", []), ensure_ascii=False),
        "deep_angles": json.dumps(a.get("deep_angles", []), ensure_ascii=False),
        "is_deep": 1 if a.get("is_deep") else 0,
    }


def upsert_article(a):
    """source_key 기준 UPSERT. created_at은 보존, updated_at만 갱신."""
    init_db()
    r = _row(a)
    with _conn() as c:
        c.execute("""
            INSERT INTO articles
              (source_key,title,lead,paragraphs,category,photo_query,pub_date,source_type,
               grade,score,ethics_score,ethics_passed,ethics_violations,deep_angles,is_deep)
            VALUES
              (:source_key,:title,:lead,:paragraphs,:category,:photo_query,:pub_date,:source_type,
               :grade,:score,:ethics_score,:ethics_passed,:ethics_violations,:deep_angles,:is_deep)
            ON CONFLICT(source_key) DO UPDATE SET
              title=excluded.title, lead=excluded.lead, paragraphs=excluded.paragraphs,
              category=excluded.category, photo_query=excluded.photo_query, pub_date=excluded.pub_date,
              source_type=excluded.source_type, grade=excluded.grade, score=excluded.score,
              ethics_score=excluded.ethics_score, ethics_passed=excluded.ethics_passed,
              ethics_violations=excluded.ethics_violations, deep_angles=excluded.deep_angles,
              is_deep=excluded.is_deep, updated_at=datetime('now')
        """, r)


def _deser(row):
    d = dict(row)
    d["paragraphs"] = json.loads(d.get("paragraphs") or "[]")
    d["ethics_violations"] = json.loads(d.get("ethics_violations") or "[]")
    d["deep_angles"] = json.loads(d.get("deep_angles") or "[]")
    d["ethics_passed"] = bool(d.get("ethics_passed"))
    return d


def get_all():
    """전체 기사 (최신 발행일 → 최근 생성 순)."""
    init_db()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM articles ORDER BY pub_date DESC, created_at DESC"
        ).fetchall()
    return [_deser(r) for r in rows]


def get_published(limit=None):
    """윤리 통과(게재 가능) 기사만."""
    return [a for a in get_all() if a["ethics_passed"]][: limit or None]


def count():
    init_db()
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]


if __name__ == "__main__":
    init_db()
    print("DB:", DB_PATH, "| 기사 수:", count())
