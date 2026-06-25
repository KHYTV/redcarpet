# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""기존 DB 기사에 단락 매칭 이미지 키워드 backfill (1회성)."""

import logging

import config
import db
from processors import deep_writer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    key = config.ANTHROPIC_API_KEY
    arts = db.get_all()
    n = 0
    for a in arts:
        if a.get("image_keywords"):
            continue  # 이미 있으면 건너뜀
        probe = {"article_title": a["title"], "article_body": "\n\n".join(a.get("paragraphs", []))}
        kws = deep_writer.image_keywords(probe, key)
        if kws:
            db.set_image_keywords(a["source_key"], kws)
            n += 1
            print(f"  [{a['title'][:30]}] → {[k['kw'] for k in kws]}")
    print(f"\nbackfill 완료: {n}건 키워드 추가")


if __name__ == "__main__":
    main()
