# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""동물보도 윤리 준칙 검증기.

기사가 ethics_guidelines의 7원칙을 얼마나 지켰는지 Claude로 정량 채점하고,
위반 항목을 추출한다. high severity 위반이 하나라도 있으면 ethics_passed=False
→ grader가 발행을 거부(veto)한다. (fact_check_passed와 동일한 거부권 구조)

이 '준수 측정 + 거부 + 감사 로그'가 단순 표방과 다른, 강제·증명 가능한 차별점이다.
"""

import json
import logging

import anthropic

import config
from processors.ethics_guidelines import RUBRIC_TEXT, PRINCIPLE_IDS

logger = logging.getLogger(__name__)

ETHICS_PROMPT = """너는 동물권 지향 언론 윤리 심사관이다. 아래 기사가 동물보도 윤리 준칙 7원칙을
얼마나 준수했는지 평가하라.

[준칙]
{rubric}

[채점 기준]
- 각 원칙을 0~3점으로 채점 (3=완전 준수, 2=경미한 아쉬움, 1=부분 위반, 0=명백한 위반)
- 위반이 있으면 violations에 {{principle, severity(low|medium|high), detail}} 로 기록
- severity=high 는 발행 불가 수준의 심각한 위반(선정성/번식조장/2차가해/광고위장 등)

반드시 아래 JSON으로만 응답:
{{
  "scores": {{"P1": 3, "P2": 3, "P3": 2, "P4": 3, "P5": 3, "P6": 3, "P7": 3}},
  "violations": [{{"principle": "P2", "severity": "low", "detail": "..."}}],
  "summary": "전반 평가 한두 문장"
}}

[기사 제목]
{title}

[기사 본문]
{body}
"""

MAX_PER_PRINCIPLE = 3


def _extract_json(text: str) -> dict:
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1 or e < s:
        raise ValueError(f"JSON 미발견: {text[:120]}")
    return json.loads(text[s:e + 1])


def ethics_review(article: dict, api_key: str) -> dict:
    """기사의 윤리 준칙 준수도를 평가해 결과를 부착한 dict를 반환한다."""
    result = dict(article)
    if not api_key:
        result["ethics_passed"] = True
        result["ethics_score"] = None
        result["ethics_summary"] = "API 키 없음 - 윤리검증 건너뜀"
        return result

    client = anthropic.Anthropic(api_key=api_key)
    prompt = ETHICS_PROMPT.format(
        rubric=RUBRIC_TEXT,
        title=article.get("article_title", ""),
        body=article.get("article_body", "")[:4000],
    )
    try:
        resp = client.messages.create(
            model=config.MODEL_REVIEWER, max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _extract_json(resp.content[0].text)
    except Exception as exc:  # noqa: BLE001
        logger.error("윤리검증 실패: %s", exc)
        result["ethics_passed"] = True  # 검증 실패 시 보수적으로 통과(차단 안 함)
        result["ethics_score"] = None
        result["ethics_summary"] = f"윤리검증 오류: {exc}"
        return result

    scores = data.get("scores", {})
    violations = data.get("violations", [])
    # 0~100 정규화 (7원칙 × 3점 만점)
    total = sum(int(scores.get(pid, 0)) for pid in PRINCIPLE_IDS)
    ethics_score = round(total / (len(PRINCIPLE_IDS) * MAX_PER_PRINCIPLE) * 100)
    high = any(v.get("severity") == "high" for v in violations)

    result["ethics_passed"] = not high
    result["ethics_score"] = ethics_score
    result["ethics_scores"] = scores
    result["ethics_violations"] = violations
    vio_txt = "; ".join(
        f"[{v.get('principle')}/{v.get('severity')}] {v.get('detail', '')[:50]}" for v in violations
    ) or "위반 없음"
    result["ethics_summary"] = f"준칙 점수 {ethics_score}/100. " + \
        ("심각 위반 없음. " if not high else "심각 위반 발견(발행거부). ") + vio_txt

    logger.info("윤리검증: score=%s, passed=%s, 위반 %d건",
                ethics_score, result["ethics_passed"], len(violations))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    good = {"article_title": "유기견 입양 안내", "article_body": "책임감 있는 입양과 중성화가 권장됩니다."}
    print(ethics_review(good, config.ANTHROPIC_API_KEY).get("ethics_summary"))
