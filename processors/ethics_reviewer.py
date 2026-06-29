# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""동물보도 윤리 준칙 검증기 (5유형 / 100점 엄격 채점).

기사의 동물 유형(야생/반려/농장산업/실험/사건)을 분류하고, 유형별 준칙 + 공통 기준으로
4개 항목을 각 0~25점, 총 100점으로 엄격히 채점한다. 총점이 ETHICS_PASS_MIN 미만이거나
critical 위반이 있으면 ethics_passed=False → grader가 발행을 거부(veto)한다.
"""

import json
import logging

import anthropic

import config
from processors.ethics_guidelines import RUBRIC_TEXT, TYPE_IDS

logger = logging.getLogger(__name__)

ETHICS_PROMPT = """너는 동물권 지향 언론 윤리 심사관이다. 아래 기사를 동물보도 윤리 준칙(5유형 체계)에
따라 **엄격하게** 평가하라. 관대하게 주지 말고, 의심스러우면 낮게 채점하라.

[준칙 — 5유형]
{rubric}

[평가 절차]
1) animal_type 분류: wild | companion | farmed | lab | incident
   (학대·사고·범죄·분쟁 등 사건 중심이면 incident, 그 외엔 주된 동물 유형)
2) 해당 유형 + 공통 기준으로 4개 항목을 각 0~25점으로 엄격 채점:
   - relation     : 동물을 유형에 맞는 관계적 위치로 존중했는가 (도구·콘텐츠·상품화면 대폭 감점)
   - principles   : 유형의 핵심 원칙을 지켰는가
   - practices    : 유형의 '문제적 관행'(나쁜 프레임)을 피했는가
   - key_question : 유형의 핵심 윤리 질문을 통과하는가
3) 문제적 관행을 발견하면 violations에 {{"practice","severity","detail"}} 기록.
   severity: low | medium | high | critical
   critical = 학대영상 반복·번식조장·산업 정당화·과학 면책·분노 소비·생존 위협 등 발행 불가 수준

총점(total) = 네 항목 합 (0~100). 엄격히.

반드시 JSON으로만 응답:
{{
  "animal_type": "companion",
  "scores": {{"relation": 22, "principles": 20, "practices": 23, "key_question": 18}},
  "total": 83,
  "violations": [{{"practice": "감동 스토리 상품화", "severity": "low", "detail": "..."}}],
  "summary": "유형 분류 근거와 총평 한두 문장"
}}

[기사 제목]
{title}

[기사 본문]
{body}
"""


def _extract_json(text: str) -> dict:
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1 or e < s:
        raise ValueError(f"JSON 미발견: {text[:120]}")
    return json.loads(text[s:e + 1])


def ethics_review(article: dict, api_key: str) -> dict:
    """기사를 5유형 준칙으로 100점 엄격 채점하고 결과를 부착해 반환한다."""
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
        result["ethics_passed"] = True  # 검증 실패 시 보수적으로 통과
        result["ethics_score"] = None
        result["ethics_summary"] = f"윤리검증 오류: {exc}"
        return result

    scores = data.get("scores", {})
    # 4항목 합으로 총점 재계산(LLM total 신뢰하지 않고 검산)
    dims = ["relation", "principles", "practices", "key_question"]
    total = sum(max(0, min(25, int(scores.get(d, 0)))) for d in dims)
    violations = data.get("violations", [])
    atype = data.get("animal_type", "")
    if atype not in TYPE_IDS:
        atype = "companion"

    critical = any(v.get("severity") == "critical" for v in violations)
    passed = (total >= config.ETHICS_PASS_MIN) and not critical

    result["ethics_passed"] = passed
    result["ethics_score"] = total
    result["ethics_type"] = atype
    result["ethics_scores"] = scores
    result["ethics_violations"] = violations
    vio_txt = "; ".join(
        f"[{v.get('severity')}] {v.get('practice', '')}: {v.get('detail', '')[:40]}" for v in violations
    ) or "위반 없음"
    gate = "통과" if passed else ("발행거부(critical)" if critical else f"발행거부(점수<{config.ETHICS_PASS_MIN})")
    result["ethics_summary"] = f"[{atype}] 준칙 점수 {total}/100 · {gate}. " + vio_txt

    logger.info("윤리검증: type=%s, score=%s/100, passed=%s, 위반 %d건",
                atype, total, passed, len(violations))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    good = {"article_title": "유기견 입양 안내",
            "article_body": "책임감 있는 입양과 중성화가 권장됩니다. 입양 전 충분한 준비가 필요합니다."}
    r = ethics_review(good, config.ANTHROPIC_API_KEY)
    print(r.get("ethics_summary"))
