"""RSS 수집기.

feedparser로 config.OVERSEAS_RSS(해외)와 config.KOREAN_NEWS_RSS(국내 구글뉴스)를
수집한다. 피드 하나가 실패해도 전체는 계속 진행한다.
"""

import logging
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
_FETCH_TIMEOUT = 20
# 국내 언론사 본문 영역에 흔히 쓰이는 셀렉터 (우선순위 순). 없으면 <p> 묶음 폴백.
_BODY_SELECTORS = [
    "article", "#article_content", ".article_content", "div[itemprop=articleBody]",
    "#articleBodyContents", "#newsct_article", ".news_view", ".article_body",
    ".cont_view", "#content", "#articeBody", ".art_text",
]


def _entry_content(entry) -> str:
    """feedparser 엔트리에서 본문 텍스트를 최대한 추출한다."""
    if getattr(entry, "summary", None):
        return entry.summary
    content = getattr(entry, "content", None)
    if content:
        try:
            return content[0].get("value", "")
        except (AttributeError, IndexError, TypeError):
            return ""
    return ""


def _collect_feed(feed_url: str, source_type: str) -> list:
    parsed = feedparser.parse(feed_url)
    if parsed.bozo and not parsed.entries:
        # 파싱 자체가 실패하고 엔트리도 없으면 실패로 간주
        raise RuntimeError(getattr(parsed, "bozo_exception", "feed parse error"))

    items = []
    now = datetime.now(timezone.utc).isoformat()
    for entry in parsed.entries:
        items.append({
            "source_type": source_type,
            "title": getattr(entry, "title", ""),
            "content": _entry_content(entry),
            "url": getattr(entry, "link", ""),
            "published": getattr(entry, "published", "") or getattr(entry, "updated", ""),
            "feed_url": feed_url,
            "collected_at": now,
        })
    return items


def collect_rss() -> list:
    """해외/국내 RSS를 모두 수집해 단일 리스트로 반환한다."""
    results = []
    feeds = [(url, "overseas_rss") for url in config.OVERSEAS_RSS]
    feeds += [(url, "korean_news") for url in config.KOREAN_NEWS_RSS]

    for feed_url, source_type in feeds:
        try:
            items = _collect_feed(feed_url, source_type)
            results.extend(items)
            logger.info("RSS 수집 [%s]: %d건 (%s)", source_type, len(items), feed_url)
        except Exception as exc:  # noqa: BLE001 - 개별 피드 실패는 무시
            logger.warning("RSS 수집 실패 (%s): %s", feed_url, exc)
            continue
    logger.info("RSS 총 수집: %d건", len(results))
    return results


def _resolve_google_news(url: str) -> str:
    """구글뉴스 RSS 인코딩 링크를 실제 기사 URL로 디코딩한다. 실패 시 원본 반환."""
    if "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import gnewsdecoder
        res = gnewsdecoder(url, interval=1)
        if res.get("status") and res.get("decoded_url"):
            return res["decoded_url"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("구글뉴스 URL 디코딩 실패: %s", exc)
    return url


def _extract_body(html: str) -> str:
    """언론사 기사 HTML에서 본문 텍스트를 best-effort로 추출한다."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    for sel in _BODY_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if len(text) > 150:
                return text
    # 폴백: 전체 <p> 합치기
    text = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
    return text if len(text) > 150 else ""


def _fetch_article_body(url: str) -> str:
    """실제 기사 URL로 이동해 본문을 가져온다. 실패 시 빈 문자열."""
    try:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        return _extract_body(resp.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("기사 본문 fetch 실패 (%s): %s", url[:60], exc)
        return ""


def enrich_korean_news(items: list) -> list:
    """korean_news 아이템의 본문을 실제 기사에서 스크래핑해 content를 보강한다.

    구글뉴스 RSS는 제목+링크만 주므로, 필터 통과 후 소수 아이템에만 적용하는 것을 권장한다.
    (디코딩+fetch가 아이템당 2회 네트워크 요청을 유발)
    """
    enriched = []
    for item in items:
        if item.get("source_type") != "korean_news":
            enriched.append(item)
            continue
        real_url = _resolve_google_news(item.get("url", ""))
        body = _fetch_article_body(real_url) if real_url else ""
        new_item = dict(item)
        if body:
            new_item["content"] = body
            new_item["resolved_url"] = real_url
            logger.info("본문 보강: %s (%d자)", item.get("title", "")[:40], len(body))
        enriched.append(new_item)
    return enriched


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for item in collect_rss()[:3]:
        print(item)
