"""웹 게시 샘플 HTML 생성.

_web_articles.json을 읽어 날짜별 섹션의 펫 매거진 페이지(output/web_sample.html)를 만든다.
이미지는 photo_query 기반 토픽 매칭 사진(loremflickr)을 첨부한다.
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
# loremflickr는 단일 키워드에서만 안정적이라 카테고리별 단일 키워드로 매핑
CAT_KEYWORD = {"dog": "dog", "cat": "cat", "health": "puppy", "training": "dog",
               "loss": "dog", "general": "pet"}

_HDR = {"User-Agent": "Mozilla/5.0"}


def img_data_uri(category, i, w=1000, h=560):
    """토픽 매칭 실제 사진을 받아 base64 data URI로 임베드. 실패 시 빈 문자열."""
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
    return f"""
    <article class="{cls}">
      <div class="hero">
        {img_html}
        <span class="badge" style="background:{color}">{label}</span>
        <span class="cap">사진: {html.escape(a.get('photo_query',''))}</span>
      </div>
      <div class="body">
        <h2>{html.escape(a.get('title',''))}</h2>
        <p class="lead">{html.escape(a.get('lead',''))}</p>
        {body if featured else ''}
        <div class="meta"><span>출처 {src}</span><span>·</span><span>{a.get('pub_date','')}</span></div>
      </div>
    </article>"""


def section(title, items, start_i):
    cards = []
    for j, a in enumerate(items):
        cards.append(card(a, start_i + j, featured=(j == 0)))
    return f'<section><h3 class="sec">{title}</h3><div class="grid">{"".join(cards)}</div></section>'


# 날짜별 그룹 (어제 먼저)
dates = sorted({a["pub_date"] for a in ART}, reverse=True)
sections = []
i = 0
for d in dates:
    items = sorted([a for a in ART if a["pub_date"] == d],
                   key=lambda x: x.get("score", 0), reverse=True)  # A등급이 대표로
    mm_dd = "·".join(d.split("-")[1:])
    label = f"{mm_dd} 발행"
    sections.append(section(label, items, i))
    i += len(items)

HTML = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RedCarpet 펫 매거진</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Apple SD Gothic Neo','Malgun Gothic',sans-serif; margin:0; background:#faf9f6; color:#1f1f1f; line-height:1.7; }}
  header.site {{ background:#fff; border-bottom:3px solid #c0392b; padding:22px 20px; text-align:center; }}
  header.site h1 {{ margin:0; font-size:28px; color:#c0392b; letter-spacing:-0.5px; }}
  header.site p {{ margin:4px 0 0; color:#888; font-size:14px; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:24px 20px 60px; }}
  h3.sec {{ font-size:15px; color:#c0392b; border-left:4px solid #c0392b; padding-left:10px; margin:34px 0 16px; }}
  .grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:22px; }}
  .card {{ background:#fff; border:1px solid #eee; border-radius:12px; overflow:hidden; display:flex; flex-direction:column; }}
  .card.featured {{ grid-column:1 / -1; }}
  .hero {{ position:relative; background:#ece9e2; aspect-ratio:16/7; overflow:hidden; }}
  .card:not(.featured) .hero {{ aspect-ratio:16/9; }}
  .hero img {{ width:100%; height:100%; object-fit:cover; display:block; }}
  .hero.noimg::after {{ content:'🐾'; position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:48px; opacity:.4; }}
  .badge {{ position:absolute; top:12px; left:12px; color:#fff; font-size:12px; padding:4px 10px; border-radius:6px; }}
  .cap {{ position:absolute; bottom:8px; right:10px; background:rgba(0,0,0,.55); color:#fff; font-size:11px; padding:2px 7px; border-radius:4px; }}
  .body {{ padding:16px 18px 18px; }}
  .body h2 {{ margin:0 0 8px; font-size:20px; line-height:1.35; }}
  .card.featured .body h2 {{ font-size:26px; }}
  .lead {{ color:#c0392b; font-size:15px; margin:0 0 10px; font-weight:500; }}
  .body p {{ margin:0 0 10px; color:#333; font-size:15px; }}
  .meta {{ display:flex; gap:6px; color:#999; font-size:13px; margin-top:6px; }}
  @media (max-width:720px) {{ .grid {{ grid-template-columns:1fr; }} }}
</style></head>
<body>
<header class="site"><h1>🐾 RedCarpet 펫 매거진</h1><p>반려동물 자동 큐레이션 · 게시 샘플</p></header>
<div class="wrap">
{''.join(sections)}
</div>
</body></html>"""

open("output/web_sample.html", "w", encoding="utf-8").write(HTML)
print("SAVED output/web_sample.html |", len(ART), "기사,", len(dates), "일자 섹션,", len(HTML), "bytes")
