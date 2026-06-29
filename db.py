# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""기사 아카이브 + SNS 인게이지먼트 DB (SQLite).

- articles: 전체 기사 누적 보관 (source_key UPSERT, 중복 방지)
- likes / comments: 반려동물 SNS 좋아요·댓글 (source_key 기준, 서버에서 공유)
웹 빌더는 articles를 읽어 누적 게재하고, server.py가 likes/comments를 읽고 쓴다.
"""

import json
import os
import sqlite3

import config

DB_PATH = os.path.join(config.OUTPUT_DIR, "redcarpet.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  source_key   TEXT PRIMARY KEY,
  title TEXT, lead TEXT, paragraphs TEXT, category TEXT, photo_query TEXT,
  pub_date TEXT, source_type TEXT, grade TEXT, score INTEGER,
  ethics_score INTEGER, ethics_passed INTEGER, ethics_violations TEXT,
  deep_angles TEXT, is_deep INTEGER, image_keywords TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS likes (
  article_key TEXT PRIMARY KEY,
  count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  article_key TEXT, name TEXT, text TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS views (
  article_key TEXT PRIMARY KEY,
  count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS videos (
  source_key TEXT PRIMARY KEY,
  title TEXT, url TEXT, category TEXT, pub_date TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS community (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, title TEXT, text TEXT,
  created_at TEXT DEFAULT (datetime('now'))
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
        # 기존 DB에 image_keywords 컬럼이 없으면 추가
        cols = [r[1] for r in c.execute("PRAGMA table_info(articles)").fetchall()]
        if "image_keywords" not in cols:
            c.execute("ALTER TABLE articles ADD COLUMN image_keywords TEXT")


# ---------- articles ----------
def _row(a):
    return {
        "source_key": a["source_key"], "title": a.get("title", ""), "lead": a.get("lead", ""),
        "paragraphs": json.dumps(a.get("paragraphs", []), ensure_ascii=False),
        "category": a.get("category", "general"), "photo_query": a.get("photo_query", "pet"),
        "pub_date": a.get("pub_date", ""), "source_type": a.get("source_type", ""),
        "grade": a.get("grade"), "score": a.get("score"),
        "ethics_score": a.get("ethics_score"),
        "ethics_passed": 1 if a.get("ethics_passed", True) else 0,
        "ethics_violations": json.dumps(a.get("ethics_violations", []), ensure_ascii=False),
        "deep_angles": json.dumps(a.get("deep_angles", []), ensure_ascii=False),
        "is_deep": 1 if a.get("is_deep") else 0,
        "image_keywords": json.dumps(a.get("image_keywords", []), ensure_ascii=False),
    }


def upsert_article(a):
    init_db()
    with _conn() as c:
        c.execute("""
            INSERT INTO articles
              (source_key,title,lead,paragraphs,category,photo_query,pub_date,source_type,
               grade,score,ethics_score,ethics_passed,ethics_violations,deep_angles,is_deep,image_keywords)
            VALUES
              (:source_key,:title,:lead,:paragraphs,:category,:photo_query,:pub_date,:source_type,
               :grade,:score,:ethics_score,:ethics_passed,:ethics_violations,:deep_angles,:is_deep,:image_keywords)
            ON CONFLICT(source_key) DO UPDATE SET
              title=excluded.title, lead=excluded.lead, paragraphs=excluded.paragraphs,
              category=excluded.category, photo_query=excluded.photo_query, pub_date=excluded.pub_date,
              source_type=excluded.source_type, grade=excluded.grade, score=excluded.score,
              ethics_score=excluded.ethics_score, ethics_passed=excluded.ethics_passed,
              ethics_violations=excluded.ethics_violations, deep_angles=excluded.deep_angles,
              is_deep=excluded.is_deep, image_keywords=excluded.image_keywords, updated_at=datetime('now')
        """, _row(a))


def set_image_keywords(source_key, kws):
    init_db()
    with _conn() as c:
        c.execute("UPDATE articles SET image_keywords=? WHERE source_key=?",
                  (json.dumps(kws, ensure_ascii=False), source_key))


def _deser(row):
    d = dict(row)
    for k in ("paragraphs", "ethics_violations", "deep_angles", "image_keywords"):
        d[k] = json.loads(d.get(k) or "[]")
    d["ethics_passed"] = bool(d.get("ethics_passed"))
    return d


def get_all():
    init_db()
    with _conn() as c:
        rows = c.execute("SELECT * FROM articles ORDER BY pub_date DESC, created_at DESC").fetchall()
    return [_deser(r) for r in rows]


def get_published(limit=None):
    return [a for a in get_all() if a["ethics_passed"]][: limit or None]


def count():
    init_db()
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]


# ---------- SNS: likes / comments ----------
def add_like(article_key):
    init_db()
    with _conn() as c:
        c.execute("INSERT INTO likes(article_key,count) VALUES(?,1) "
                  "ON CONFLICT(article_key) DO UPDATE SET count=count+1", (article_key,))
        return c.execute("SELECT count FROM likes WHERE article_key=?", (article_key,)).fetchone()[0]


def add_comment(article_key, name, text):
    init_db()
    name = (name or "익명").strip()[:40]
    text = (text or "").strip()[:500]
    if not text:
        return None
    with _conn() as c:
        c.execute("INSERT INTO comments(article_key,name,text) VALUES(?,?,?)",
                  (article_key, name, text))
    return {"name": name, "text": text}


def add_view(article_key):
    init_db()
    with _conn() as c:
        c.execute("INSERT INTO views(article_key,count) VALUES(?,1) "
                  "ON CONFLICT(article_key) DO UPDATE SET count=count+1", (article_key,))
        return c.execute("SELECT count FROM views WHERE article_key=?", (article_key,)).fetchone()[0]


def add_video(source_key, title, url, category="general", pub_date=""):
    init_db()
    with _conn() as c:
        c.execute("INSERT INTO videos(source_key,title,url,category,pub_date) VALUES(?,?,?,?,?) "
                  "ON CONFLICT(source_key) DO UPDATE SET title=excluded.title, url=excluded.url, "
                  "category=excluded.category, pub_date=excluded.pub_date",
                  (source_key, title, url, category, pub_date))


def get_videos():
    init_db()
    with _conn() as c:
        rows = c.execute("SELECT * FROM videos ORDER BY pub_date DESC, created_at DESC").fetchall()
    return [dict(r) for r in rows]


def add_community_post(name, title, text):
    init_db()
    name = (name or "익명").strip()[:40] or "익명"
    title = (title or "").strip()[:120]
    text = (text or "").strip()[:2000]
    if not (title or text):
        return None
    with _conn() as c:
        cur = c.execute("INSERT INTO community(name,title,text) VALUES(?,?,?)", (name, title, text))
        pid = cur.lastrowid
        row = c.execute("SELECT * FROM community WHERE id=?", (pid,)).fetchone()
    return {"key": f"c:{row['id']}", "name": row["name"], "title": row["title"],
            "text": row["text"], "created_at": row["created_at"]}


def get_community():
    init_db()
    with _conn() as c:
        rows = c.execute("SELECT * FROM community ORDER BY id DESC").fetchall()
    return [{"key": f"c:{r['id']}", "name": r["name"], "title": r["title"],
             "text": r["text"], "created_at": r["created_at"]} for r in rows]


def _empty():
    return {"likes": 0, "comments": [], "views": 0}


def get_engagement():
    """{source_key: {likes, comments[], views}} 전체 반환."""
    init_db()
    eng = {}
    with _conn() as c:
        for r in c.execute("SELECT article_key,count FROM likes").fetchall():
            eng.setdefault(r["article_key"], _empty())["likes"] = r["count"]
        for r in c.execute("SELECT article_key,count FROM views").fetchall():
            eng.setdefault(r["article_key"], _empty())["views"] = r["count"]
        for r in c.execute("SELECT article_key,name,text,created_at FROM comments ORDER BY id ASC").fetchall():
            eng.setdefault(r["article_key"], _empty())["comments"].append(
                {"name": r["name"], "text": r["text"], "created_at": r["created_at"]})
    return eng


if __name__ == "__main__":
    init_db()
    print("DB:", DB_PATH, "| 기사:", count(), "| 인게이지먼트:", len(get_engagement()))
