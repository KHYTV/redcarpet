# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""2단계 심층 기사 작성기 (Deep Writer).

1단계에서 추려진 A등급 '씨앗 기사'를 받아:
  ① 확장 각도 도출 (LLM)
  ② 관련 내용 수집 — 배치 내 교차참조 + Google 웹검색 + PubMed(의료)
  ③ 씨앗 + 수집 컨텍스트를 통합한 심층 기사 작성 (윤리 준칙 주입)
자체 팩트체크/윤리/등급은 deep_pipeline에서 기존 모듈로 수행한다.
"""

import json
import logging
import re

import anthropic

import config
from processors.ethics_guidelines import CONSTITUTION_TEXT
from processors.fact_checker import _search_pubmed, _search_google

logger = logging.getLogger(__name__)

ANGLE_PROMPT = """다음 씨앗 기사를 더 깊이 있는 심층 기사로 확장하려 한다.
독자에게 가치를 더할 '확장 각도' 3~5개를 도출하라. 각 각도는 배경·원인·전문가 관점·
실용 팁·정책/제도 등 씨앗에 없던 깊이를 더하는 것이어야 한다.

각 각도에 category(health|medical|nutrition|behavior|general)와 검색어(search_query, 한국어)를 부여.
반드시 JSON으로만:
{{"angles": [{{"angle": "확장 각도", "category": "behavior", "search_query": "검색어"}}]}}

[씨앗 기사 제목] {title}
[씨앗 기사 본문] {body}
"""

SYNTHESIS_PROMPT = """너는 동물권 지향 심층 기사 전문 기자다. 아래 씨앗 기사와 수집된 관련 자료를
통합하여 한 편의 깊이 있는 심층 기사를 작성하라.

요건:
- 씨앗의 단편 정보를 넘어 배경·원인·다각도 관점·실용적 조언까지 포괄 (4~6단락)
- 수집 자료의 사실만 활용하고, 불확실하면 단정하지 말 것
- 원문 인용 금지, 완전 재작성

{constitution}

반드시 JSON으로만:
{{"title": "심층 기사 제목", "body": "본문(4~6단락, 단락 사이 빈 줄)", "summary": "- 핵심1\\n- 핵심2\\n- 핵심3"}}

[씨앗 기사 제목] {title}
[씨앗 기사 본문] {body}

[수집된 관련 자료]
{context}
"""

STOPWORDS = {"있다", "한다", "위해", "그리고", "하지만", "the", "and", "for", "with", "그는", "또한"}


def _extract_json(text: str) -> dict:
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1 or e < s:
        raise ValueError(f"JSON 미발견: {text[:120]}")
    return json.loads(text[s:e + 1])


def _keywords(text: str) -> set:
    """간단 키워드 토큰화 (한글 2자+/영문 3자+ 토큰)."""
    toks = re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", (text or "").lower())
    return {t for t in toks if t not in STOPWORDS}


def find_related(seed: dict, items: list, top: int = 5) -> list:
    """수집 배치에서 씨앗과 키워드가 겹치는 관련 아이템 top개."""
    seed_kw = _keywords(seed.get("article_title", "") + " " + seed.get("article_body", "") +
                        " " + seed.get("title", ""))
    seed_url = seed.get("url", "")
    scored = []
    for it in items:
        if it.get("url") and it.get("url") == seed_url:
            continue
        kw = _keywords(it.get("title", "") + " " + it.get("content", ""))
        overlap = len(seed_kw & kw)
        if overlap >= 2:
            scored.append((overlap, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:top]]


def _gather_context(angles: list, related_items: list) -> str:
    """각 각도별로 배치 교차참조 + Google/PubMed 검색 결과를 텍스트로 모은다."""
    blocks = []
    # 배치 내 관련 기사 요약
    if related_items:
        rel = "\n".join(f"- (배치 관련기사) {it.get('title','')[:60]}: {(it.get('content','') or '')[:120]}"
                        for it in related_items)
        blocks.append("[배치 내 관련 기사]\n" + rel)
    # 각 각도별 외부 검색
    for ang in angles:
        cat = ang.get("category", "general")
        q = ang.get("search_query", ang.get("angle", ""))
        try:
            if cat in ("health", "medical"):
                ev = _search_pubmed(q)
            else:
                ev = _search_google(q)
        except Exception as exc:  # noqa: BLE001
            logger.warning("심층 검색 실패(%s): %s", q[:30], exc)
            ev = "검색 실패"
        blocks.append(f"[각도: {ang.get('angle','')[:40]}]\n{ev}")
    return "\n\n".join(blocks)


def write_deep_article(seed: dict, related_items: list, api_key: str) -> dict:
    """씨앗 기사 → 심층 기사 dict (article_title/article_body/article_summary 부착)."""
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 필요합니다.")
    client = anthropic.Anthropic(api_key=api_key)
    title = seed.get("article_title", "") or seed.get("title", "")
    body = seed.get("article_body", "") or seed.get("content", "")

    # ① 확장 각도
    resp = client.messages.create(
        model=config.MODEL_WRITER, max_tokens=1000,
        messages=[{"role": "user", "content": ANGLE_PROMPT.format(title=title, body=body[:3000])}],
    )
    angles = _extract_json(resp.content[0].text).get("angles", [])
    logger.info("심층 각도 %d개 도출", len(angles))

    # ② 관련 내용 수집
    context = _gather_context(angles, related_items)

    # ③ 심층 통합 작성
    resp = client.messages.create(
        model=config.MODEL_WRITER, max_tokens=3500,
        messages=[{"role": "user", "content": SYNTHESIS_PROMPT.format(
            constitution=CONSTITUTION_TEXT, title=title, body=body[:3000], context=context[:5000])}],
    )
    data = _extract_json(resp.content[0].text)

    deep = dict(seed)
    deep.update({
        "article_title": data.get("title", title),
        "article_body": data.get("body", ""),
        "article_summary": data.get("summary", ""),
        "deep_angles": [a.get("angle", "") for a in angles],
        "is_deep": True,
        "seed_title": title,
    })
    # 1단계 점수/등급은 재평가 대상이므로 초기화
    for k in ("score", "grade", "action", "fact_check_passed", "ethics_passed", "ethics_score"):
        deep.pop(k, None)
    logger.info("심층 기사 작성 완료: %s (%d자)", deep["article_title"][:30], len(deep["article_body"]))
    return deep


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed = {"article_title": "강아지가 풀을 먹는 이유",
            "article_body": "건강한 강아지가 가끔 풀을 먹는 것은 정상이다."}
    out = write_deep_article(seed, [], config.ANTHROPIC_API_KEY)
    print(out["article_title"], "\n", out["article_body"][:200])
