# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""Reddit 수집기 (old.reddit.com HTML 스크래핑).

공식 JSON API와 신 UI는 데이터센터/일부 IP에서 403으로 차단되므로,
상대적으로 접근 가능한 old.reddit.com HTML을 파싱한다.

ToS상 비공식 경로이므로 정상 트래픽처럼 동작하도록:
  - 요청 간 지연(REQUEST_DELAY)
  - 단일 세션 재사용
  - 점수 미달 게시물은 본문 fetch 생략(요청 최소화)
실패한 서브레딧/게시물은 건너뛰고 전체는 계속한다.

향후 OAuth(PRAW) 승격: REDDIT_CLIENT_ID/SECRET가 생기면 이 모듈을 PRAW 기반으로
교체하거나 fetch 경로를 분기하면 된다. 현재는 스크래핑 단일 경로.
"""

import logging
import os
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

BASE = "https://old.reddit.com"
LISTING_URL = BASE + "/r/{subreddit}/hot/"
# old.reddit은 일반 브라우저 UA에서 가장 안정적으로 응답한다.
USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
REQUEST_DELAY = 2.5  # 초, 모든 요청 사이 지연 (politeness)
TIMEOUT = 20
POSTS_PER_SUB = 10

# 본문 fetch 대상: 셀프(텍스트) 게시물만. 외부 링크 글은 본문이 없다.
_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


def _get(url: str) -> str:
    resp = _session.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _parse_listing(html: str) -> list:
    """hot 목록 페이지에서 게시물 메타데이터를 추출한다."""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for thing in soup.select("div.thing[data-fullname]"):
        if thing.get("data-promoted") == "true":  # 광고
            continue
        if thing.get("data-stickied") == "true":  # 공지
            continue
        title_el = thing.select_one("a.title")
        if not title_el:
            continue
        permalink = thing.get("data-permalink", "")
        domain = thing.get("data-domain", "")
        # data-timestamp는 에포크 밀리초. 작성 시각을 ISO로 변환(정렬·날짜 필터용).
        published = ""
        ts = thing.get("data-timestamp")
        if ts:
            try:
                published = datetime.fromtimestamp(int(ts) / 1000, timezone.utc).isoformat()
            except (ValueError, TypeError):
                published = ""
        posts.append({
            "title": title_el.get_text().strip(),
            "permalink": permalink,
            "url": "https://www.reddit.com" + permalink,
            "score": int(thing.get("data-score") or 0),
            "comments": int(thing.get("data-comments-count") or 0),
            "is_self": domain.startswith("self."),
            "published": published,
        })
    return posts


def _fetch_body(permalink: str) -> str:
    """게시물 페이지에서 본문(selftext)을 추출한다. 실패 시 빈 문자열."""
    try:
        time.sleep(REQUEST_DELAY)
        html = _get(BASE + permalink)
        soup = BeautifulSoup(html, "html.parser")
        # 첫 linklisting 항목의 usertext-body가 게시물 본문(댓글 아님)
        body = soup.select_one(
            "div.sitetable.linklisting div.thing div.entry div.usertext-body div.md"
        )
        return body.get_text("\n").strip() if body else ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("본문 fetch 실패 (%s): %s", permalink, exc)
        return ""


def _collect_one(subreddit: str, fetch_body: bool, posts_per_sub: int) -> list:
    time.sleep(REQUEST_DELAY)
    html = _get(LISTING_URL.format(subreddit=subreddit))
    posts = _parse_listing(html)[:posts_per_sub]

    now = datetime.now(timezone.utc).isoformat()
    items = []
    for p in posts:
        body = ""
        # 요청 절약: 점수 통과 + 셀프 게시물만 본문 fetch
        if fetch_body and p["is_self"] and p["score"] >= config.MIN_REDDIT_SCORE:
            body = _fetch_body(p["permalink"])
        items.append({
            "source_type": "reddit",
            "subreddit": subreddit,
            "title": p["title"],
            "content": body,
            "url": p["url"],
            "score": p["score"],
            "published": p.get("published", ""),
            "collected_at": now,
        })
    return items


def collect_reddit(fetch_body: bool = True, posts_per_sub: int = POSTS_PER_SUB) -> list:
    """config.SUBREDDITS의 hot 게시물을 old.reddit 스크래핑으로 수집한다.

    fetch_body=False면 본문 없이 목록 메타데이터만 빠르게 수집한다.
    """
    results = []
    for subreddit in config.SUBREDDITS:
        try:
            items = _collect_one(subreddit, fetch_body, posts_per_sub)
            results.extend(items)
            logger.info("Reddit r/%s 수집: %d건", subreddit, len(items))
        except Exception as exc:  # noqa: BLE001 - 개별 서브레딧 실패는 무시
            logger.warning("Reddit r/%s 수집 실패: %s", subreddit, exc)
            continue
    logger.info("Reddit 총 수집: %d건", len(results))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for item in collect_reddit()[:3]:
        print(item)
