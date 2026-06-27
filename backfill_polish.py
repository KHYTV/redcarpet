# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""기존 DB 기사 본문에 기사형 문장 교정(polish) 적용 (1회성)."""

import logging

import config
import db
from processors import deep_writer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def _split(body):
    parts = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(parts) < 2:
        parts = [p.strip() for p in body.split("\n") if p.strip()]
    return parts


def main():
    key = config.ANTHROPIC_API_KEY
    arts = db.get_all()
    for a in arts:
        body = "\n\n".join(a.get("paragraphs", []))
        if not body:
            continue
        polished = deep_writer.polish_body(body, key)
        a["paragraphs"] = _split(polished)
        db.upsert_article(a)
        print(f"  교정: {a['title'][:34]}")
    print(f"\n문장 교정 완료: {len(arts)}건")


if __name__ == "__main__":
    main()
