# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""웹 게시 샘플 HTML 생성 (RedCar Pet — 윤리 준칙 검증판).

_web_articles.json을 읽어 RedCar Pet 펫 매거진 페이지(output/web_sample.html)를 만든다.
- 윤리 준칙 통과 기사만 게재하고, 각 기사에 윤리 준칙 점수 배지를 표시한다.
- 준칙 거부(ethics_passed=False) 기사는 '편집 보류'로 별도 표기해 차별점을 보여준다.
- 이미지는 photo_query 기반 토픽 매칭 사진(loremflickr)을 base64로 임베드한다.
"""

import base64
import html
import json

import requests

ART = json.load(open("output/results/_web_articles.json", encoding="utf-8"))

CAT_LABEL = {"dog": "반려견", "cat": "반려묘", "health": "건강", "training": "훈련",
             "loss": "반려동물 추모", "general": "소식"}
CAT_COLOR = {"dog": "#1D9E75", "cat": "#7F77DD", "health": "#378ADD", "training": "#BA7517",
             "loss": "#D4537E", "general": "#5F5E5A"}
CAT_KEYWORD = {"dog": "dog", "cat": "cat", "health": "puppy", "training": "dog",
               "loss": "dog", "general": "pet"}

_HDR = {"User-Agent": "Mozilla/5.0"}


def img_data_uri(category, i, w=1000, h=560):
    kw = CAT_KEYWORD.get(category, "pet")
    try:
        r = requests.get(f"https://loremflickr.com/{w}/{h}/{kw}?lock={i+7}",
                         headers=_HDR, timeout=25, allow_redirects=True)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            b64 = base64.b64encode(r.content).decode("ascii")
            print(f"  이미지 [{category}/{kw}] {len(r.content)//1024}KB 임베드")
            return f"data:image/jpeg;base64,{b64}"
    except Exception as exc:  # noqa: BLE001
        print(f"  이미지 실패 [{category}]: {exc}")
    return ""


def ethics_badge(score):
    """윤리 준칙 점수 배지 색상(점수대별)."""
    if score is None:
        return "#5F5E5A", "미평가"
    if score >= 90:
        return "#0F6E56", f"윤리 준칙 {score}"
    if score >= 70:
        return "#854F0B", f"윤리 준칙 {score}"
    return "#A32D2D", f"윤리 준칙 {score}"


def card(a, i, featured=False):
    cat = a.get("category", "general")
    color = CAT_COLOR.get(cat, "#5F5E5A")
    label = CAT_LABEL.get(cat, "소식")
    src = "레딧" if a.get("source_type") == "reddit" else "국내뉴스"
    paras = "".join(f"<p>{html.escape(p)}</p>" for p in a.get("paragraphs", []))
    body = paras if featured else f"<p>{html.escape(a.get('lead',''))}</p>"
    cls = "card featured" if featured else "card"
    uri = img_data_uri(cat, i)
    img_html = (f'<img src="{uri}" alt="{html.escape(a.get("title",""))}">' if uri
                else f'<div class="noimg" style="background:{color}"></div>')
    e_color, e_text = ethics_badge(a.get("ethics_score"))
    n_ang = len(a.get("deep_angles", []))
    deep_meta = f'<span>심층 {n_ang}각도 통합</span><span>·</span>' if n_ang else ''
    return f"""
    <article class="{cls}">
      <div class="hero">
        {img_html}
        <span class="badge" style="background:{color}">{label}</span>
        <span class="deepmark">심층</span>
        <span class="ethics" style="background:{e_color}"><span class="dot">✓</span> {e_text}</span>
        <span class="cap">사진: {html.escape(a.get('photo_query',''))}</span>
      </div>
      <div class="body">
        <h2>{html.escape(a.get('title',''))}</h2>
        <p class="lead">{html.escape(a.get('lead',''))}</p>
        {body if featured else ''}
        <div class="meta">{deep_meta}<span>출처 {src}</span><span>·</span><span>{a.get('pub_date','')}</span></div>
      </div>
    </article>"""


def section(title, items, start_i):
    cards = []
    for j, a in enumerate(items):
        cards.append(card(a, start_i + j, featured=(j == 0)))
    return f'<section><h3 class="sec">{title}</h3><div class="grid">{"".join(cards)}</div></section>'


# 윤리 준칙 통과/거부 분리
published = [a for a in ART if a.get("ethics_passed", True)]
rejected = [a for a in ART if not a.get("ethics_passed", True)]

dates = sorted({a["pub_date"] for a in published}, reverse=True)
sections = []
i = 0
for d in dates:
    items = sorted([a for a in published if a["pub_date"] == d],
                   key=lambda x: (x.get("ethics_score") or 0, x.get("score", 0)), reverse=True)
    mm_dd = "·".join(d.split("-")[1:])
    sections.append(section(f"{mm_dd} 발행", items, i))
    i += len(items)

# 준칙 미게재 블록
rejected_html = ""
if rejected:
    rows = "".join(
        f'<li><b>{html.escape(r["title"])}</b> — 윤리 준칙 {r.get("ethics_score","?")}점, '
        f'위반 {", ".join(v.get("principle","") for v in r.get("ethics_violations",[]))} '
        f'(예: {html.escape((r.get("ethics_violations") or [{}])[0].get("detail","")[:50])})</li>'
        for r in rejected
    )
    rejected_html = f"""
    <section class="held">
      <h3 class="sec held-h">⛔ 윤리 준칙 미달로 게재 보류 ({len(rejected)}건)</h3>
      <p class="held-desc">사실·품질은 충족했으나 동물보도 윤리 준칙 위반으로 자동 발행 거부된 기사입니다.</p>
      <ul>{rows}</ul>
    </section>"""

avg = round(sum(a.get("ethics_score") or 0 for a in published) / max(len(published), 1))

HTML = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RedCar Pet — 동물권 지향 펫 매거진</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Apple SD Gothic Neo','Malgun Gothic',sans-serif; margin:0; background:#faf9f6; color:#1f1f1f; line-height:1.7; }}
  header.site {{ background:#fff; border-bottom:3px solid #c0392b; padding:22px 20px; text-align:center; }}
  header.site h1 {{ margin:0; font-size:30px; color:#c0392b; letter-spacing:-0.5px; }}
  header.site .tag {{ margin:4px 0 0; color:#666; font-size:14px; }}
  header.site .ethics-line {{ margin-top:8px; display:inline-block; background:#0F6E56; color:#fff; font-size:13px; padding:4px 12px; border-radius:20px; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:24px 20px 60px; }}
  h3.sec {{ font-size:15px; color:#c0392b; border-left:4px solid #c0392b; padding-left:10px; margin:34px 0 16px; }}
  .grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:22px; }}
  .card {{ background:#fff; border:1px solid #eee; border-radius:12px; overflow:hidden; display:flex; flex-direction:column; }}
  .card.featured {{ grid-column:1 / -1; }}
  .hero {{ position:relative; background:#ece9e2; aspect-ratio:16/7; overflow:hidden; }}
  .card:not(.featured) .hero {{ aspect-ratio:16/9; }}
  .hero img {{ width:100%; height:100%; object-fit:cover; display:block; }}
  .badge {{ position:absolute; top:12px; left:12px; color:#fff; font-size:12px; padding:4px 10px; border-radius:6px; }}
  .deepmark {{ position:absolute; top:12px; left:74px; background:#1f1f1f; color:#fff; font-size:12px; padding:4px 9px; border-radius:6px; font-weight:500; }}
  .ethics {{ position:absolute; top:12px; right:12px; color:#fff; font-size:12px; padding:4px 10px; border-radius:6px; font-weight:500; }}
  .ethics .dot {{ font-weight:700; }}
  .cap {{ position:absolute; bottom:8px; right:10px; background:rgba(0,0,0,.55); color:#fff; font-size:11px; padding:2px 7px; border-radius:4px; }}
  .body {{ padding:16px 18px 18px; }}
  .body h2 {{ margin:0 0 8px; font-size:20px; line-height:1.35; }}
  .card.featured .body h2 {{ font-size:26px; }}
  .lead {{ color:#c0392b; font-size:15px; margin:0 0 10px; font-weight:500; }}
  .body p {{ margin:0 0 10px; color:#333; font-size:15px; }}
  .meta {{ display:flex; gap:6px; color:#999; font-size:13px; margin-top:6px; }}
  .held {{ margin-top:36px; background:#fbeeee; border:1px solid #f0d0d0; border-radius:12px; padding:6px 20px 16px; }}
  .held-h {{ color:#A32D2D; border-left-color:#A32D2D; }}
  .held-desc {{ color:#7a4a4a; font-size:14px; margin:0 0 8px; }}
  .held ul {{ margin:0; padding-left:18px; color:#5a3a3a; font-size:14px; }}
  .held li {{ margin-bottom:6px; }}
  @media (max-width:720px) {{ .grid {{ grid-template-columns:1fr; }} }}
</style></head>
<body>
<header class="site">
  <h1>🐾 RedCar Pet</h1>
  <div class="tag">동물권 지향 AI 심층 저널리즘 · 게시 샘플</div>
  <div class="ethics-line">✓ 2단계 심층 보도 · 동물보도 윤리 준칙 검증 · 게재 평균 {avg}점</div>
</header>
<div class="wrap">
{''.join(sections)}
{rejected_html}
</div>
</body></html>"""

open("output/web_sample.html", "w", encoding="utf-8").write(HTML)
print(f"SAVED | 게재 {len(published)}건(평균 윤리 {avg}점), 보류 {len(rejected)}건, {len(HTML)} bytes")
