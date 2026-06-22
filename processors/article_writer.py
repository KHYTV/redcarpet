# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""기사 작성기.

수집/필터링된 아이템을 Claude(Haiku)로 한국어 실용 기사로 재작성한다.
원문 인용 없이 완전 재작성하고, 제목/본문/핵심요약으로 파싱한다.
"""

import logging
import time
from datetime import datetime, timezone

import anthropic

import config
from processors.ethics_guidelines import CONSTITUTION_TEXT

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """다음 반려동물 관련 콘텐츠를 한국 반려동물 오너를 위한 실용적인 한국어 기사로 작성해줘.
원문 인용 절대 금지, 완전 재작성.
전문용어는 쉬운 언어로 변환.

""" + CONSTITUTION_TEXT + """


출력 형식 (반드시 아래 머리말을 그대로 사용):
[제목]
(한 줄 제목)

[본문]
(3~4단락)

[핵심요약]
- 요약 1
- 요약 2
- 요약 3

입력
제목: {title}
내용: {content}
출처: {source_type}
"""


def _parse_article(text: str) -> dict:
    """[제목]/[본문]/[핵심요약] 섹션으로 분리한다."""
    sections = {"제목": "", "본문": "", "핵심요약": ""}
    current = None
    buffer = {"제목": [], "본문": [], "핵심요약": []}

    for line in text.splitlines():
        stripped = line.strip()
        header = stripped.strip("[]").strip()
        if header in sections and stripped.startswith("["):
            current = header
            continue
        if current:
            buffer[current].append(line)

    title = "\n".join(buffer["제목"]).strip()
    body = "\n".join(buffer["본문"]).strip()
    summary = "\n".join(buffer["핵심요약"]).strip()

    # 파싱 실패 시 전체 텍스트를 본문으로 폴백
    if not body and not title:
        body = text.strip()
    return {"title": title, "body": body, "summary": summary}


def _write_one(client: "anthropic.Anthropic", item: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=item.get("title", ""),
        content=(item.get("content", "") or "")[:4000],
        source_type=item.get("source_type", ""),
    )
    resp = client.messages.create(
        model=config.MODEL_WRITER,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    parsed = _parse_article(text)

    article = dict(item)
    article.update({
        "article_title": parsed["title"] or item.get("title", ""),
        "article_body": parsed["body"],
        "article_summary": parsed["summary"],
        "written_at": datetime.now(timezone.utc).isoformat(),
    })
    return article


def write_articles(items: list, api_key: str) -> list:
    """아이템 리스트를 기사 리스트로 변환한다. 호출당 REQUEST_INTERVAL 간격을 둔다."""
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 필요합니다.")
    client = anthropic.Anthropic(api_key=api_key)

    articles = []
    for idx, item in enumerate(items):
        try:
            article = _write_one(client, item)
            articles.append(article)
            logger.info("기사 작성 %d/%d: %s", idx + 1, len(items), article["article_title"][:40])
        except Exception as exc:  # noqa: BLE001
            logger.error("기사 작성 실패 (%s): %s", item.get("title", "")[:30], exc)
        # 마지막 항목 뒤에는 대기하지 않는다
        if idx < len(items) - 1:
            time.sleep(config.REQUEST_INTERVAL)
    return articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = [{
        "title": "How often should I walk my dog?",
        "content": "Most dogs need at least 2 walks a day...",
        "source_type": "reddit",
    }]
    for a in write_articles(sample, config.ANTHROPIC_API_KEY):
        print(a)
