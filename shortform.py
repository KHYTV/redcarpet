# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""기사 → 숏폼 영상(세로 9:16, 스틸컷 슬라이드쇼 + 자막) 자동 생성.

1) generate_script: 기사를 60초 이내 장면 스크립트로 각색(Claude)
2) render: 각 장면을 정지 이미지 + 한글 자막 슬라이드(PIL 1080x1920)로 합성
   → imageio-ffmpeg 번들 ffmpeg로 장면별 길이만큼 이어붙여 MP4 인코딩(무음)

TTS 내레이션·BGM은 후속 확장 여지(현재는 무음 슬라이드쇼).
"""

import io
import json
import logging
import os
import subprocess

import anthropic
import imageio_ffmpeg
import requests
from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

W, H = 1080, 1920           # 세로형 9:16
FONT_BD = "C:/Windows/Fonts/malgunbd.ttf"
FONT_RG = "C:/Windows/Fonts/malgun.ttf"
MAX_TOTAL = 58              # 총 길이 상한(초) — 60초 이내 보장
ACCENT = (192, 57, 43)      # #c0392b
_HDR = {"User-Agent": "Mozilla/5.0"}

SCRIPT_PROMPT = """다음 반려동물 기사를 60초 이내 '세로형 숏폼 영상'으로 각색한다.
정지 이미지 슬라이드 + 자막 형식. 장면 6~8개.

각 장면:
- caption: 화면에 뜰 자막(한 줄 12~24자, 임팩트 있게, 이모지 금지)
- image_kw: 장면에 어울리는 사진 검색어(영어 2~4단어, 예: "senior dog resting")
- seconds: 3~8 (정수)

규칙:
- 첫 장면은 강한 후킹 문구, 마지막 장면은 핵심 메시지+행동 유도.
- 모든 seconds 합이 55초를 넘지 않게.
- 사실 왜곡·선정성 금지, 동물권 존중.

반드시 JSON으로만:
{{"title":"영상 제목(한국어)","scenes":[{{"caption":"...","image_kw":"...","seconds":5}}],"hashtags":["#반려동물"]}}

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
    scenes = [s for s in data.get("scenes", []) if s.get("caption")]
    # 60초 이내로 클램프
    total = sum(int(s.get("seconds", 4)) for s in scenes)
    if total > MAX_TOTAL:
        f = MAX_TOTAL / total
        for s in scenes:
            s["seconds"] = max(2, round(int(s.get("seconds", 4)) * f))
    data["scenes"] = scenes
    return data


def _fetch_image(keyword, lock):
    try:
        kw = (keyword or "pet").strip().replace(" ", ",")
        r = requests.get(f"https://loremflickr.com/{W}/{H}/{kw}?lock={lock}",
                         headers=_HDR, timeout=25)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.warning("이미지 실패 [%s]: %s", keyword, exc)
    return Image.new("RGB", (W, H), (40, 40, 44))


def _cover(img):
    """1080x1920를 꽉 채우도록 스케일 후 중앙 크롭."""
    iw, ih = img.size
    scale = max(W / iw, H / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    nw, nh = img.size
    return img.crop(((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W, (nh - H) // 2 + H))


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            lines.append(cur); cur = ch
    if cur:
        lines.append(cur)
    return lines


def _make_slide(scene, idx, first=False, last=False):
    img = _cover(_fetch_image(scene.get("image_kw"), 7000 + idx))
    # 하단 그라데이션(가독성)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for y in range(H):
        if y > H * 0.45:
            a = int(200 * (y - H * 0.45) / (H * 0.55))
            od.line([(0, y), (W, y)], fill=(0, 0, 0, min(a, 200)))
    base = Image.alpha_composite(img.convert("RGBA"), ov)
    d = ImageDraw.Draw(base)

    # 브랜드 + AI 표시
    d.text((44, 44), "🐾 RedCar Pet", font=ImageFont.truetype(FONT_BD, 40), fill=(255, 255, 255))
    tag_font = ImageFont.truetype(FONT_RG, 30)
    tw = d.textlength("AI 제작", font=tag_font)
    d.rounded_rectangle((W - tw - 84, 48, W - 40, 96), radius=16, fill=(139, 91, 238))
    d.text((W - tw - 62, 54), "AI 제작", font=tag_font, fill=(255, 255, 255))

    # 자막
    fsize = 78 if first or last else 66
    font = ImageFont.truetype(FONT_BD, fsize)
    lines = _wrap(d, scene["caption"], font, W - 140)
    lh = fsize + 22
    total_h = lh * len(lines)
    y = H - 360 - total_h if not first else int(H * 0.62)
    for ln in lines:
        w = d.textlength(ln, font=font)
        x = (W - w) / 2
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)):  # 외곽선
            d.text((x + dx, y + dy), ln, font=font, fill=(0, 0, 0))
        d.text((x, y), ln, font=font, fill=(255, 255, 255))
        y += lh

    # 하단 진행 악센트 바
    d.rectangle((0, H - 14, W, H), fill=ACCENT)
    return base.convert("RGB")


def render(article, api_key, out_path=None, script=None):
    script = script or generate_script(article, api_key)
    scenes = script["scenes"]
    tmp = os.path.join(config.OUTPUT_DIR, "_sf_frames")
    os.makedirs(tmp, exist_ok=True)
    listf = os.path.join(tmp, "list.txt")
    lines = []
    for i, sc in enumerate(scenes):
        p = os.path.join(tmp, f"s{i:02d}.png")
        _make_slide(sc, i, first=(i == 0), last=(i == len(scenes) - 1)).save(p)
        dur = max(2, int(sc.get("seconds", 4)))
        lines.append(f"file '{p.replace(os.sep, '/')}'\nduration {dur}")
    lines.append(f"file '{os.path.join(tmp, f's{len(scenes)-1:02d}.png').replace(os.sep, '/')}'")
    open(listf, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    out_path = out_path or os.path.join(config.OUTPUT_DIR, "shortform_sample.mp4")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", listf,
           "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
           "-movflags", "+faststart", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 실패: " + (r.stderr or "")[-500:])
    dur = sum(max(2, int(s.get("seconds", 4))) for s in scenes)
    logger.info("숏폼 렌더 완료: %s (%d장면, %d초)", out_path, len(scenes), dur)
    return {"path": out_path, "seconds": dur, "scenes": len(scenes), "script": script}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    import db
    arts = [a for a in db.get_all() if a.get("ethics_passed", True)]
    art = arts[0]
    print("대상 기사:", art["title"])
    res = render(art, config.ANTHROPIC_API_KEY)
    print(json.dumps({k: v for k, v in res.items() if k != "script"}, ensure_ascii=False))
    print("\n스크립트:")
    for i, s in enumerate(res["script"]["scenes"]):
        print(f"  {i+1}. [{s['seconds']}s] {s['caption']}  (img: {s['image_kw']})")
