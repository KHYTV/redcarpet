# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""투명한 AI 펫 페르소나 — 정전(canon) + 누적 기억 + 현실 접지로 일관된 게시물 생성.

페르소나는 가상의 반려동물 캐릭터다(🤖AI 표시). 핵심 사실(정전)은 고정하고,
게시물·이벤트가 기억으로 누적되어 일관성을 유지한다. 합성 데이터이므로
보험/연금/상조 등 데이터 자산에는 절대 편입하지 않는다(is_ai=1로 격리).
"""

import logging
from datetime import datetime, timezone, timedelta

import anthropic

import config
import db

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

SAFETY_PROMPT = """다음은 반려동물 SNS의 짧은 1인칭 게시물이다. 동물권 관점에서 '명백한 문제'만 가려라:
학대 미화, 펫숍·무분별 번식 조장, 동물 비하·상품화, 잔혹/선정적 묘사.
일상적·긍정적·정보성 글은 문제없음으로 둔다.
반드시 JSON으로만: {{"ok": true, "reason": "간단 사유"}}

[게시물]
{text}
"""

POST_PROMPT = """너는 '{name}'라는 반려동물 캐릭터로서 SNS 커뮤니티에 짧은 글을 한 편 쓴다.
아래 [정전]은 절대 바뀌지 않는 너의 핵심 설정이다. 반드시 일관되게 지켜라(품종·나이·성격 등).

[정전 — 고정]
- 이름: {name} / 종: {species} / 품종: {breed} / 나이: {birth}
- 성격: {personality}
- 말투: {tone}
- 관심사: {interests}
- 배경: {backstory}

[지금까지의 내 기억 — 일관성 유지용]
{summary}
{recent}

[오늘의 맥락]
{context}

작성 규칙:
- 1인칭(반려동물 시점), 위 말투로 짧게(2~4문장). 과장·선정성 금지.
- 정전·기억과 모순되지 않게. 이전 글을 자연스럽게 이어가도 좋다.
- 동물권 관점(존중·책임)에서 벗어나지 말 것.
- image_kw: 이 글에 어울리는 사진 검색어를 영어 2~4단어로(반드시 품종 포함). 예: "golden retriever swimming", "golden retriever park friend".

반드시 JSON으로만: {{"text": "게시물 본문", "image_kw": "english photo keywords"}}
"""


def _season(now):
    m = now.month
    return {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄",
            6: "여름", 7: "여름", 8: "여름", 9: "가을", 10: "가을", 11: "가을"}[m]


def _extract_json(text):
    s, e = text.find("{"), text.rfind("}")
    return __import__("json").loads(text[s:e + 1])


def seed_default():
    """기본 페르소나 1개(골든리트리버 '래')를 정전으로 등록."""
    db.upsert_persona({
        "id": "rae",
        "name": "래", "species": "강아지", "breed": "골든리트리버", "birth": "3살",
        "personality": "활발하고 다정함. 호기심 많고 사람을 잘 따름.",
        "tone": "친근한 반말, 이모지 적당히, 밝고 따뜻하게",
        "interests": "산책, 물놀이, 간식, 새 친구 사귀기",
        "backstory": "보호소에서 입양된 골든리트리버. 책임감 있는 보호자와 함께 산다.",
    })
    return "rae"


def generate_post(pid, api_key, post=True):
    """페르소나의 일관된 게시물 1편 생성 → 기억 누적 + (옵션) 커뮤니티 게시."""
    p = db.get_persona(pid)
    if not p:
        raise ValueError(f"persona 없음: {pid}")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 필요")

    now = datetime.now(timezone.utc).astimezone(KST)
    mem = db.get_persona_memory(pid)
    recent = "\n".join(f"- ({m['kind']}) {m['content']}" for m in mem) or "- (아직 기억 없음)"
    summary = p.get("summary") or "(요약 없음)"
    context = f"{now.strftime('%Y-%m-%d')} · 계절: {_season(now)}"

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=config.MODEL_WRITER, max_tokens=600,
        messages=[{"role": "user", "content": POST_PROMPT.format(
            name=p["name"], species=p["species"], breed=p["breed"], birth=p["birth"],
            personality=p["personality"], tone=p["tone"], interests=p["interests"],
            backstory=p["backstory"], summary=summary, recent=recent, context=context)}],
    )
    out = _extract_json(resp.content[0].text)
    text = out.get("text", "").strip()
    image_kw = (out.get("image_kw") or "").strip()
    if not text:
        return None

    # 가벼운 안전 점검(명백한 동물권 위반만 차단 — 캐주얼 글에 맞게)
    try:
        sr = client.messages.create(
            model=config.MODEL_REVIEWER, max_tokens=200,
            messages=[{"role": "user", "content": SAFETY_PROMPT.format(text=text)}])
        if _extract_json(sr.content[0].text).get("ok") is False:
            logger.warning("페르소나 글 안전 점검 차단, 폐기: %s", text[:40])
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("안전 점검 오류(통과 처리): %s", exc)

    db.add_persona_memory(pid, "post", text)  # 기억 누적
    if post:
        db.add_community_post(f"{p['name']} 🤖AI", "", text, is_ai=1, image_kw=image_kw)
    logger.info("[%s] 게시물 생성: %s", p["name"], text[:50])
    return text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    pid = seed_default()
    for i in range(3):
        print(f"\n--- 게시물 {i+1} ---")
        print(generate_post(pid, config.ANTHROPIC_API_KEY))
