# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""기사 → 카드뉴스형 숏폼 영상(세로 9:16) 자동 생성.

1) generate_script: 기사를 '카드뉴스'로 압축 각색(Claude) — 카드마다 이모지·핵심 한마디·보조설명
2) render: 각 카드를 브랜드 그라데이션 + 컬러 이모지 + 큰 타이포로 디자인(PIL 1080x1920)
   → imageio-ffmpeg 번들 ffmpeg로 카드별 길이만큼 이어붙여 MP4(무음)

스톡 사진에 의존하지 않는 그래픽 카드 디자인이라 안정적이고 정보 전달에 최적.
개별 카드 PNG도 저장해 이미지 카드뉴스로도 활용 가능.
"""

import io
import json
import logging
import os
import subprocess

import anthropic
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

W, H = 1080, 1920
FONT_BD = "C:/Windows/Fonts/malgunbd.ttf"
FONT_RG = "C:/Windows/Fonts/malgun.ttf"
FONT_EMOJI = "C:/Windows/Fonts/seguiemj.ttf"
MAX_TOTAL = 55

# 카드 배경 그라데이션(위→아래) — 모두 흰 글씨가 잘 보이는 친근한 톤
PALETTES = [
    ((255, 107, 107), (192, 57, 43)),    # coral → red (브랜드)
    ((91, 124, 250), (59, 79, 176)),     # blue
    ((43, 192, 168), (18, 128, 106)),    # teal
    ((255, 159, 69), (232, 106, 44)),    # orange
    ((139, 91, 238), (91, 55, 176)),     # purple
    ((255, 122, 158), (198, 60, 110)),   # pink
]

SCRIPT_PROMPT = """다음 반려동물 기사를 '카드뉴스' 형식의 세로형 숏폼으로 각색한다.
정보를 압축하고 재미있게. 카드 6~8장.

각 카드:
- emoji: 카드 내용을 상징하는 이모지 딱 1개 (예: 🐶 💊 🏥 💛 ⏰ ✅ 💰 🩺)
- headline: 핵심 한마디 (한 줄, 6~18자, 굵고 임팩트 있게)
- sub: 보조 설명 (한 줄, 최대 32자. 없으면 빈 문자열)
- seconds: 3~6 (정수)

규칙:
- 첫 카드 = 강한 후킹(제목형), 마지막 카드 = 핵심 요약 또는 행동 유도.
- 숫자·핵심 키워드로 압축. 장황한 문장 금지, 한 카드 = 한 메시지.
- 사실 왜곡·선정성·감정 과잉 금지, 동물권 존중.

반드시 JSON으로만:
{{"title":"카드뉴스 제목(한국어)","scenes":[{{"emoji":"🐶","headline":"...","sub":"...","seconds":4}}],"hashtags":["#반려동물"]}}

[기사 제목] {title}
[기사 본문]
{body}
"""


def generate_script(article, api_key):
    client = anthropic.Anthropic(api_key=api_key)
    body = "\n".join(article.get("paragraphs", [])) or article.get("lead", "")
    resp = client.messages.create(
        model=config.MODEL_WRITER, max_tokens=1500,
        messages=[{"role": "user", "content": SCRIPT_PROMPT.format(
            title=article.get("title", ""), body=body[:3000])}])
    t = resp.content[0].text
    data = json.loads(t[t.find("{"):t.rfind("}") + 1])
    scenes = [s for s in data.get("scenes", []) if s.get("headline")]
    total = sum(int(s.get("seconds", 4)) for s in scenes)
    if total > MAX_TOTAL:
        f = MAX_TOTAL / total
        for s in scenes:
            s["seconds"] = max(2, round(int(s.get("seconds", 4)) * f))
    data["scenes"] = scenes
    return data


def _font(path, size):
    return ImageFont.truetype(path, size)


def _gradient(top, bottom):
    base = Image.new("RGB", (W, H))
    px = base.load()
    for y in range(H):
        t = y / H
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    return base


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in (text or "").split(" "):
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        if draw.textlength(word, font=font) > max_w:  # 한 단어가 너무 길면 글자 단위
            s = ""
            for ch in word:
                if draw.textlength(s + ch, font=font) <= max_w:
                    s += ch
                else:
                    lines.append(s); s = ch
            cur = s
        else:
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _text_center(d, cx, y, text, font, fill=(255, 255, 255), shadow=True):
    w = d.textlength(text, font=font)
    x = cx - w / 2
    if shadow:
        d.text((x + 2, y + 3), text, font=font, fill=(0, 0, 0, 120))
    d.text((x, y), text, font=font, fill=fill)


def _emoji_center(d, cx, cy, ch, size):
    try:
        f = _font(FONT_EMOJI, size)
        bb = d.textbbox((0, 0), ch, font=f, embedded_color=True)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        d.text((cx - w / 2 - bb[0], cy - h / 2 - bb[1]), ch, font=f, embedded_color=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("이모지 렌더 실패(%s): %s", ch, exc)


def _make_card(scene, idx, n, cover=False):
    top, bottom = PALETTES[0] if cover else PALETTES[idx % len(PALETTES)]
    card = _gradient(top, bottom)
    d = ImageDraw.Draw(card)

    # 상단 라벨 + 번호 + AI 제작
    d.text((60, 62), "RedCar Pet · 카드뉴스", font=_font(FONT_BD, 38), fill=(255, 255, 255))
    num = f"{idx + 1} / {n}"
    nf = _font(FONT_BD, 36)
    nw = d.textlength(num, font=nf)
    d.text((W - nw - 60, 64), num, font=nf, fill=(255, 255, 255, 220))
    tagf = _font(FONT_RG, 28)
    tw = int(d.textlength("AI 제작", font=tagf))
    pill_l = W - 60 - tw - 40
    d.rounded_rectangle((pill_l, 110, W - 60, 158), radius=16, fill=(255, 255, 255))
    d.text((pill_l + 20, 117), "AI 제작", font=tagf, fill=bottom)  # 배경색(진한 톤) 글씨

    # 중앙: 이모지 + 헤드라인 + 서브
    _emoji_center(d, W / 2, H * 0.30, scene.get("emoji", "🐾"), 300 if cover else 260)

    hl = scene.get("headline", "")
    hf = _font(FONT_BD, 100 if cover else 88)
    hlines = _wrap(d, hl, hf, W - 150)
    lh = (100 if cover else 88) + 26
    y = H * 0.46
    for ln in hlines:
        _text_center(d, W / 2, y, ln, hf)
        y += lh

    sub = scene.get("sub", "")
    if sub:
        sf = _font(FONT_RG, 50)
        y += 18
        for ln in _wrap(d, sub, sf, W - 200):
            _text_center(d, W / 2, y, ln, sf, fill=(255, 255, 255, 235))
            y += 66

    # 하단: 진행 점 + 푸터
    dot_r, gap = 9, 34
    total_w = n * gap
    sx = (W - total_w) / 2 + gap / 2
    inactive = tuple((255 + bottom[k]) // 2 for k in range(3))  # 흐린 점(비활성)
    for i in range(n):
        c = (255, 255, 255) if i == idx else inactive
        cx = sx + i * gap
        d.ellipse((cx - dot_r, H - 150 - dot_r, cx + dot_r, H - 150 + dot_r), fill=c)
    _text_center(d, W / 2, H - 96, "매일 반려동물 뉴스 · RedCar Pet", _font(FONT_RG, 32),
                 fill=(255, 255, 255), shadow=False)
    return card


def render(article, api_key, out_path=None, script=None, save_cards=True):
    script = script or generate_script(article, api_key)
    scenes = script["scenes"]
    n = len(scenes)
    tmp = os.path.join(config.OUTPUT_DIR, "_sf_frames")
    os.makedirs(tmp, exist_ok=True)
    lines = []
    for i, sc in enumerate(scenes):
        p = os.path.join(tmp, f"s{i:02d}.png")
        _make_card(sc, i, n, cover=(i == 0)).save(p)
        dur = max(2, int(sc.get("seconds", 4)))
        lines.append(f"file '{p.replace(os.sep, '/')}'\nduration {dur}")
    lines.append(f"file '{os.path.join(tmp, f's{n-1:02d}.png').replace(os.sep, '/')}'")
    listf = os.path.join(tmp, "list.txt")
    open(listf, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    out_path = out_path or os.path.join(config.OUTPUT_DIR, "shortform_sample.mp4")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", listf,
           "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
           "-movflags", "+faststart", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 실패: " + (r.stderr or "")[-500:])
    # 포스터(첫 카드)
    Image.open(os.path.join(tmp, "s00.png")).resize((540, 960), Image.LANCZOS).save(
        os.path.splitext(out_path)[0] + ".jpg", quality=85)
    dur = sum(max(2, int(s.get("seconds", 4))) for s in scenes)
    logger.info("카드뉴스 숏폼 완료: %s (%d카드, %d초)", out_path, n, dur)
    return {"path": out_path, "seconds": dur, "cards": n, "script": script}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    import db
    arts = [a for a in db.get_all() if a.get("ethics_passed", True)]
    art = arts[0]
    print("대상 기사:", art["title"])
    res = render(art, config.ANTHROPIC_API_KEY)
    print(json.dumps({k: v for k, v in res.items() if k != "script"}, ensure_ascii=False))
    print("\n카드 스크립트:")
    for i, s in enumerate(res["script"]["scenes"]):
        print(f"  {i+1}. [{s['seconds']}s] {s.get('emoji','')} {s['headline']} — {s.get('sub','')}")
