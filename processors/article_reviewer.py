# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""기사 검수/교정 + 점수 산출.

Claude로 4개 항목(각 25점)을 평가하고 교정본(revised_article)을 받아
article_body를 교체한다. 팩트체크 요약을 프롬프트에 포함한다.
"""

import json
import logging
import re

import anthropic

import config

logger = logging.getLogger(__name__)

# 본문에 새어 들어오는 구조 마커/편집자 주석 정리용
_SECTION_HEAD = re.compile(r"^\s*\[[^\]]{1,20}\]\s*$")          # [기사 제목] 같은 헤더 단독 줄
_EDITOR_NOTE = re.compile(r"\[편집자\s*주[:：][^\]]*\]")          # [편집자 주: ...] 인라인 주석


def _clean_revised(text: str) -> str:
    """교정본에서 구조 마커([기사 본문] 등)와 편집자 주석을 제거해 순수 본문만 남긴다."""
    if not text:
        return text
    # [기사 본문] 섹션이 있으면 그 이후만 취함
    if "[기사 본문]" in text:
        text = text.split("[기사 본문]", 1)[1]
    # 뒤따르는 다른 섹션은 잘라냄
    for marker in ("[핵심요약]", "[편집자 주]", "[편집자주]"):
        if marker in text:
            text = text.split(marker, 1)[0]
    out = []
    for line in text.splitlines():
        if _SECTION_HEAD.match(line):          # 대괄호 헤더 단독 줄 제거
            continue
        out.append(_EDITOR_NOTE.sub("", line))  # 인라인 편집자 주석 제거
    return "\n".join(out).strip()

REVIEW_PROMPT = """다음 한국어 반려동물 기사를 검수/교정하고 점수를 매겨줘.

평가 기준 (각 25점, 총 100점):
1. 정보 정확성 (accuracy_score)
2. 가독성 (readability_score)
3. 실용성 (utility_score)
4. 완성도 (completeness_score)

팩트체크 결과를 반드시 반영해 교정해줘:
{fact_check_summary}

반드시 아래 JSON 형식으로만 응답:
{{
  "score": 85,
  "accuracy_score": 22,
  "readability_score": 20,
  "utility_score": 23,
  "completeness_score": 20,
  "corrections": "수정한 사항 요약",
  "feedback": "개선 방향",
  "revised_article": "교정된 기사 본문 전문 (순수 본문 텍스트만. [기사 제목]·[기사 본문]·[편집자 주] 같은 마커나 머리말 금지)"
}}

[기사 제목]
{article_title}

[기사 본문]
{article_body}
"""


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"JSON 미발견: {text[:120]}")
    return json.loads(text[start : end + 1])


def review_article(article: dict, api_key: str) -> dict:
    """기사를 검수/교정하고 점수 필드를 부착해 반환한다."""
    result = dict(article)
    if not api_key:
        result.setdefault("score", 0)
        result["review_error"] = "API 키 없음"
        return result

    client = anthropic.Anthropic(api_key=api_key)
    prompt = REVIEW_PROMPT.format(
        fact_check_summary=article.get("fact_check_summary", "(없음)"),
        article_title=article.get("article_title", ""),
        article_body=article.get("article_body", "")[:4000],
    )

    try:
        resp = client.messages.create(
            model=config.MODEL_REVIEWER,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extract_json(resp.content[0].text)
    except Exception as exc:  # noqa: BLE001
        logger.error("검수 실패: %s", exc)
        result.setdefault("score", 0)
        result["review_error"] = str(exc)
        return result

    result.update({
        "score": int(data.get("score", 0)),
        "accuracy_score": data.get("accuracy_score", 0),
        "readability_score": data.get("readability_score", 0),
        "utility_score": data.get("utility_score", 0),
        "completeness_score": data.get("completeness_score", 0),
        "corrections": data.get("corrections", ""),
        "feedback": data.get("feedback", ""),
    })
    # 교정본으로 본문 교체 (있을 때만). 구조 마커/편집자 주석 정리.
    revised = _clean_revised(data.get("revised_article", "").strip())
    if revised:
        result["article_body"] = revised

    logger.info("검수 완료: score=%s (%s)", result["score"], result.get("article_title", "")[:30])
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = {
        "article_title": "강아지 산책 가이드",
        "article_body": "강아지는 하루 2회 산책이 필요합니다.",
        "fact_check_summary": "심각한 오류 없음.",
    }
    print(review_article(sample, config.ANTHROPIC_API_KEY).get("score"))
