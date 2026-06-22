# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""숏폼 대본 생성기.

A등급 기사를 Claude로 숏폼(세로형) 대본 JSON으로 변환한다.
훅/장면/플랫폼별 해시태그·제목을 포함한다.
"""

import json
import logging

import anthropic

import config

logger = logging.getLogger(__name__)

SCRIPT_PROMPT = """다음 한국어 반려동물 기사를 60초 이내의 세로형 숏폼 대본으로 만들어줘.
장면은 5~8개, 각 장면 duration의 합은 60초 이내.

반드시 아래 JSON 형식으로만 응답:
{{
  "hook": "첫 3초 훅 문장",
  "total_duration": 45,
  "scenes": [
    {{
      "scene_no": 1,
      "duration": 5,
      "caption": "자막(2줄 이내, 줄당 10자 이내)",
      "narration": "나레이션 텍스트",
      "visual_prompt": "Kling AI용 영어 영상 프롬프트 (반려동물 배경)",
      "caption_position": "top|center|bottom"
    }}
  ],
  "hashtags": {{
    "youtube_shorts": ["#반려동물"],
    "instagram_reels": ["#펫스타그램"],
    "tiktok": ["#반려동물"],
    "naver_clip": ["#반려동물"]
  }},
  "title_per_platform": {{
    "youtube_shorts": "제목",
    "instagram_reels": "제목",
    "tiktok": "제목",
    "naver_clip": "제목"
  }}
}}

[기사 제목]
{article_title}

[기사 본문]
{article_body}

[핵심요약]
{article_summary}
"""


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"JSON 미발견: {text[:120]}")
    return json.loads(text[start : end + 1])


def generate_script(article: dict, api_key: str) -> dict:
    """기사 dict → 숏폼 대본 dict."""
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 필요합니다.")
    client = anthropic.Anthropic(api_key=api_key)
    prompt = SCRIPT_PROMPT.format(
        article_title=article.get("article_title", ""),
        article_body=article.get("article_body", "")[:4000],
        article_summary=article.get("article_summary", ""),
    )
    resp = client.messages.create(
        model=config.MODEL_WRITER,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    script = _extract_json(resp.content[0].text)
    logger.info("대본 생성: %d개 장면, %s초", len(script.get("scenes", [])), script.get("total_duration"))
    return script


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = {
        "article_title": "강아지 산책, 하루 몇 번이 적당할까",
        "article_body": "반려견 건강을 위해 하루 2~3회 산책이 권장됩니다.",
        "article_summary": "· 소형견 2회\n· 대형견 3회 이상",
    }
    print(json.dumps(generate_script(sample, config.ANTHROPIC_API_KEY), ensure_ascii=False, indent=2))
