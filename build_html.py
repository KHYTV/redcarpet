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

import db

# DB(누적 아카이브)에서 전체 기사를 읽어 기존+신규를 함께 게재
ART = db.get_all()
if not ART:  # DB 비어있으면 과거 JSON으로 폴백
    try:
        ART = json.load(open("output/results/_web_articles.json", encoding="utf-8"))
    except Exception:
        ART = []

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
    cls = "card featured" if featured else "card"
    uri = img_data_uri(cat, i)
    img_html = (f'<img src="{uri}" alt="{html.escape(a.get("title",""))}">' if uri
                else f'<div class="noimg" style="background:{color}"></div>')
    e_color, e_text = ethics_badge(a.get("ethics_score"))
    n_ang = len(a.get("deep_angles", []))
    deep_meta = f'<span>심층 {n_ang}각도 통합</span><span>·</span>' if n_ang else ''
    return f"""
    <article class="{cls}" onclick="openArt({i})" tabindex="0" role="button" aria-label="전문 보기: {html.escape(a.get('title',''))}">
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
        <div class="meta">{deep_meta}<span>출처 {src}</span><span>·</span><span>{a.get('pub_date','')}</span></div>
        <span class="readmore">기사 전문 보기 →</span>
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
flat = []  # 렌더 순서대로의 기사 (모달 인덱스와 일치)
i = 0
for d in dates:
    items = sorted([a for a in published if a["pub_date"] == d],
                   key=lambda x: (x.get("ethics_score") or 0, x.get("score", 0)), reverse=True)
    mm_dd = "·".join(d.split("-")[1:])
    sections.append(section(f"{mm_dd} 발행", items, i))
    flat.extend(items)
    i += len(items)

# 모달용 기사 데이터 (전문 포함)
arts_js = json.dumps([
    {
        "title": a.get("title", ""),
        "lead": a.get("lead", ""),
        "paragraphs": a.get("paragraphs", []),
        "label": CAT_LABEL.get(a.get("category", "general"), "소식"),
        "color": CAT_COLOR.get(a.get("category", "general"), "#5F5E5A"),
        "date": a.get("pub_date", ""),
        "ethics": a.get("ethics_score"),
        "src": "레딧" if a.get("source_type") == "reddit" else "국내뉴스",
        "angles": a.get("deep_angles", []),
    }
    for a in flat
], ensure_ascii=False)

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
  .card {{ background:#fff; border:1px solid #eee; border-radius:12px; overflow:hidden; display:flex; flex-direction:column; cursor:pointer; transition:box-shadow .15s, transform .15s; }}
  .card:hover {{ box-shadow:0 6px 20px rgba(0,0,0,.10); transform:translateY(-2px); }}
  .card:focus {{ outline:2px solid #c0392b; outline-offset:2px; }}
  .card.featured {{ grid-column:1 / -1; }}
  .readmore {{ display:inline-block; margin-top:10px; color:#c0392b; font-size:14px; font-weight:500; }}
  .overlay {{ position:fixed; inset:0; background:rgba(0,0,0,.55); display:none; align-items:flex-start; justify-content:center; padding:40px 16px; overflow-y:auto; z-index:100; }}
  .overlay.open {{ display:flex; }}
  .modal {{ background:#fff; max-width:720px; width:100%; border-radius:14px; overflow:hidden; }}
  .modal-band {{ height:8px; }}
  .modal-inner {{ padding:26px 30px 34px; }}
  .modal .tags {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; font-size:13px; }}
  .modal .tag {{ padding:3px 10px; border-radius:6px; color:#fff; }}
  .modal h2 {{ font-size:26px; line-height:1.35; margin:0 0 12px; color:#1a1a1a; }}
  .modal .mlead {{ color:#c0392b; font-size:16px; font-weight:500; margin:0 0 18px; line-height:1.6; }}
  .modal .mbody p {{ font-size:16px; line-height:1.8; color:#333; margin:0 0 14px; }}
  .modal .angles {{ margin-top:20px; padding:14px 16px; background:#f6f5f1; border-radius:10px; font-size:13px; color:#555; }}
  .modal .angles b {{ color:#333; font-weight:500; }}
  .modal-close {{ float:right; cursor:pointer; font-size:22px; color:#999; line-height:1; border:none; background:none; }}
  @media (max-width:720px) {{ .modal-inner {{ padding:20px; }} .modal h2 {{ font-size:22px; }} }}
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

<div class="overlay" id="overlay" onclick="if(event.target===this)closeArt()">
  <div class="modal" role="dialog" aria-modal="true">
    <div class="modal-band" id="m-band"></div>
    <div class="modal-inner">
      <button class="modal-close" onclick="closeArt()" aria-label="닫기">✕</button>
      <div class="tags" id="m-tags"></div>
      <h2 id="m-title"></h2>
      <p class="mlead" id="m-lead"></p>
      <div class="mbody" id="m-body"></div>
      <div class="angles" id="m-angles"></div>
    </div>
  </div>
</div>

<script>
const ARTS = {arts_js};
const ov = document.getElementById('overlay');
function esc(s){{return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
function openArt(i){{
  const a = ARTS[i]; if(!a) return;
  document.getElementById('m-band').style.background = a.color;
  document.getElementById('m-title').textContent = a.title;
  document.getElementById('m-lead').textContent = a.lead;
  document.getElementById('m-body').innerHTML = a.paragraphs.map(p=>'<p>'+esc(p)+'</p>').join('');
  document.getElementById('m-tags').innerHTML =
    '<span class="tag" style="background:'+a.color+'">'+esc(a.label)+'</span>'+
    '<span class="tag" style="background:#1f1f1f">심층</span>'+
    '<span class="tag" style="background:#0F6E56">✓ 윤리 준칙 '+(a.ethics??'-')+'</span>'+
    '<span style="color:#999;align-self:center">출처 '+esc(a.src)+' · '+esc(a.date)+'</span>';
  document.getElementById('m-angles').innerHTML = a.angles && a.angles.length
    ? '<b>심층 확장 각도 '+a.angles.length+'개</b><br>'+a.angles.map(x=>'· '+esc(x)).join('<br>') : '';
  ov.classList.add('open'); document.body.style.overflow='hidden';
}}
function closeArt(){{ ov.classList.remove('open'); document.body.style.overflow=''; }}
document.addEventListener('keydown', e=>{{ if(e.key==='Escape') closeArt(); }});
</script>
</body></html>"""

open("output/web_sample.html", "w", encoding="utf-8").write(HTML)
print(f"SAVED | 게재 {len(published)}건(평균 윤리 {avg}점), 보류 {len(rejected)}건, {len(HTML)} bytes")
