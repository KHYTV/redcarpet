# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""동물보도 윤리 준칙 (Animal Reporting Ethics Constitution).

동물권 지향 언론보도를 위한 7원칙을 코드화한다. 이 준칙은:
  - 생성 시: article_writer 프롬프트에 '헌법'으로 주입되어 준수를 유도
  - 검증 시: ethics_reviewer가 각 원칙 준수도를 정량 채점
  - 등급 시: 심각 위반은 grader에서 발행 거부(veto)
참고: 해외 동물 미디어 윤리 프레임워크(animalsandmedia.org 등)를 참고해
한국 반려·동물 보도 맥락에 맞게 정리했다. 편집 철학에 따라 수정 가능.
"""

# 각 원칙: id, 이름, 설명, 위반 예시(검증 기준 명확화용)
PRINCIPLES = [
    {
        "id": "P1",
        "name": "생명 존중·비도구화",
        "desc": "동물을 상품·수단·도구가 아닌 감응적 존재(sentient being)로 서술한다.",
        "violation_example": "동물을 단순 상품·재화로만 취급, '물건' 취급하는 표현",
    },
    {
        "id": "P2",
        "name": "선정성 배제",
        "desc": "학대·죽음·고통을 자극적으로 묘사하거나 클릭베이트로 소비하지 않는다.",
        "violation_example": "잔혹 묘사 과장, 충격·공포 유발 제목, 고통의 흥미 위주 소비",
    },
    {
        "id": "P3",
        "name": "정확성·종 특이성",
        "desc": "품종·종별 차이를 정확히 다루고, 근거 없는 의인화를 경계한다.",
        "violation_example": "검증 안 된 단정, 종 특성 무시, 과도한 의인화로 사실 왜곡",
    },
    {
        "id": "P4",
        "name": "입양·복지 지향",
        "desc": "펫숍·무분별 번식·유기를 조장하는 표현을 지양하고 입양·중성화·책임보호를 권장한다.",
        "violation_example": "충동구매·번식 조장, 유기 정당화, 책임 없는 분양 미화",
    },
    {
        "id": "P5",
        "name": "존중하는 언어",
        "desc": "비하·혐오·차별적 표현을 쓰지 않고, 동물을 개체로 존중하는 언어를 사용한다.",
        "violation_example": "비하·혐오 표현, 동물을 멸시하는 호칭",
    },
    {
        "id": "P6",
        "name": "약자·보호자 배려",
        "desc": "상실·슬픔을 겪는 보호자나 취약한 대상에 대한 2차 가해를 방지한다.",
        "violation_example": "유족·보호자 비난, 슬픔의 흥미 위주 소비, 2차 가해",
    },
    {
        "id": "P7",
        "name": "이해상충 투명성",
        "desc": "홍보성 콘텐츠를 구분하고, 특정 업체를 무비판적으로 홍보하지 않는다.",
        "violation_example": "광고를 기사로 위장, 특정 상품·업체 무비판 홍보",
    },
]

# 생성 프롬프트 주입용 헌법 텍스트
CONSTITUTION_TEXT = "[동물보도 윤리 준칙 — 아래 7원칙을 반드시 지켜 작성할 것]\n" + "\n".join(
    f"{p['id']}. {p['name']}: {p['desc']}" for p in PRINCIPLES
)

# 검증 프롬프트용 (위반 예시 포함)
RUBRIC_TEXT = "\n".join(
    f"{p['id']} {p['name']}: {p['desc']} (위반 예: {p['violation_example']})"
    for p in PRINCIPLES
)

PRINCIPLE_IDS = [p["id"] for p in PRINCIPLES]
