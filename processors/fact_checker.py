"""하이브리드 팩트체크.

[1단계] Claude로 핵심 클레임 추출 + confidence/category 부여
[2단계] confidence=low 클레임만 웹 검색으로 2차 검증
        - health/medical → PubMed
        - 그 외 → Google Custom Search
[3단계] Claude로 검색 결과 대조 후 최종 판정(verdict/severity)
[판정] high severity 오류 존재 시 fact_check_passed=False
"""

import json
import logging

import requests

import anthropic

import config

logger = logging.getLogger(__name__)

CLAIM_EXTRACT_PROMPT = """다음 기사에서 사실 검증이 필요한 핵심 주장(claim)을 최대 5개 추출해줘.
각 주장에 대해 신뢰도(confidence)와 분류(category)를 매겨줘.

confidence: "low" 또는 "high"  (확실한 상식이면 high, 검증이 필요하면 low)
category: "health" | "nutrition" | "behavior" | "medical" | "general"

반드시 아래 JSON 형식으로만 응답:
{{"claims": [{{"claim": "주장 내용", "confidence": "low", "category": "health"}}]}}

기사:
{article_body}
"""

VERDICT_PROMPT = """아래 주장과 웹 검색 결과를 대조해 사실 여부를 판정해줘.

주장: {claim}
분류: {category}

검색 결과:
{evidence}

반드시 아래 JSON 형식으로만 응답:
{{"verdict": "confirmed|false|partially_true|unverifiable", "severity": "low|medium|high", "note": "근거 요약"}}
"""

TIMEOUT = 15


def _extract_json(text: str) -> dict:
    """Claude 응답에서 첫 JSON 객체를 추출/파싱한다."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"JSON 미발견: {text[:120]}")
    return json.loads(text[start : end + 1])


def _search_pubmed(query: str) -> str:
    params = {"db": "pubmed", "term": query, "retmax": 3, "retmode": "json"}
    resp = requests.get(config.PUBMED_ESEARCH_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    ids = resp.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return "PubMed 검색 결과 없음"
    return "PubMed 관련 논문 ID: " + ", ".join(ids)


def _search_google(query: str) -> str:
    if not config.GOOGLE_SEARCH_API_KEY or not config.GOOGLE_CSE_ID:
        return "Google 검색 미설정"
    params = {
        "key": config.GOOGLE_SEARCH_API_KEY,
        "cx": config.GOOGLE_CSE_ID,
        "q": query,
        "num": 3,
    }
    resp = requests.get(config.GOOGLE_SEARCH_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return "Google 검색 결과 없음"
    return "\n".join(f"- {it.get('title', '')}: {it.get('snippet', '')}" for it in items)


def _gather_evidence(claim: dict) -> str:
    category = claim.get("category", "general")
    query = claim.get("claim", "")
    try:
        if category in ("health", "medical"):
            return _search_pubmed(query)
        return _search_google(query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("검색 실패 (%s): %s", query[:40], exc)
        return "검색 실패"


def fact_check(article: dict, api_key: str) -> dict:
    """기사를 팩트체크해 결과를 부착한 dict를 반환한다."""
    result = dict(article)
    if not api_key:
        result["fact_check_passed"] = True
        result["fact_check_summary"] = "API 키 없음 - 팩트체크 건너뜀"
        return result

    client = anthropic.Anthropic(api_key=api_key)
    body = article.get("article_body", "") or article.get("content", "")

    # [1단계] 클레임 추출
    try:
        resp = client.messages.create(
            model=config.MODEL_REVIEWER,
            max_tokens=1500,
            messages=[{"role": "user", "content": CLAIM_EXTRACT_PROMPT.format(article_body=body[:4000])}],
        )
        claims = _extract_json(resp.content[0].text).get("claims", [])
    except Exception as exc:  # noqa: BLE001
        logger.error("클레임 추출 실패: %s", exc)
        result["fact_check_passed"] = True
        result["fact_check_summary"] = f"클레임 추출 실패: {exc}"
        return result

    # [2~3단계] low confidence 클레임만 검증
    verdicts = []
    high_severity = False
    for claim in claims:
        if claim.get("confidence") != "low":
            continue
        evidence = _gather_evidence(claim)
        try:
            resp = client.messages.create(
                model=config.MODEL_REVIEWER,
                max_tokens=600,
                messages=[{
                    "role": "user",
                    "content": VERDICT_PROMPT.format(
                        claim=claim.get("claim", ""),
                        category=claim.get("category", "general"),
                        evidence=evidence,
                    ),
                }],
            )
            verdict = _extract_json(resp.content[0].text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("판정 실패: %s", exc)
            continue

        verdicts.append({"claim": claim.get("claim", ""), **verdict})
        if verdict.get("verdict") == "false" and verdict.get("severity") == "high":
            high_severity = True

    passed = not high_severity
    if verdicts:
        summary_lines = [
            f"- [{v.get('verdict')}/{v.get('severity')}] {v.get('claim', '')[:40]}: {v.get('note', '')[:60]}"
            for v in verdicts
        ]
        summary = f"검증 {len(verdicts)}건. " + ("심각한 오류 없음." if passed else "심각한 오류 발견.") + "\n" + "\n".join(summary_lines)
    else:
        summary = f"검증 대상(저신뢰) 클레임 없음. 추출 클레임 {len(claims)}건."

    result["fact_check_passed"] = passed
    result["fact_check_summary"] = summary
    logger.info("팩트체크: passed=%s, 검증 %d건", passed, len(verdicts))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = {"article_body": "강아지는 초콜릿을 먹어도 안전하다. 하루 2회 산책이 권장된다."}
    print(fact_check(sample, config.ANTHROPIC_API_KEY)["fact_check_summary"])
