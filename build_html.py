# Copyright (c) 2026 RedCarpet Project. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""웹 게시 샘플 HTML 생성 (RedCar Pet — 페이스북형 뉴스피드).

DB(누적 아카이브)에서 기사를 읽어 페이스북 피드 스타일로 렌더링한다.
- 단일 컬럼 피드(아바타·헤더·이미지·액션바)
- 카드 클릭 → 전문 모달, 본문 단락 사이에 내용 부합 이미지 3장 삽입
- 모든 이미지는 base64 임베드(자체완결·오프라인)
- 윤리 준칙 점수 배지 / 준칙 미달은 '게재 보류' 표기
"""

import base64
import html
import json

import requests

import db

ART = db.get_all()
if not ART:
    try:
        ART = json.load(open("output/results/_web_articles.json", encoding="utf-8"))
    except Exception:
        ART = []

CAT_LABEL = {"dog": "반려견", "cat": "반려묘", "health": "건강", "training": "훈련",
             "loss": "반려동물 추모", "general": "소식"}
CAT_COLOR = {"dog": "#1D9E75", "cat": "#7F77DD", "health": "#378ADD", "training": "#BA7517",
             "loss": "#D4537E", "general": "#5F5E5A"}
CAT_EMOJI = {"dog": "🐶", "cat": "🐱", "health": "🩺", "training": "🦴",
             "loss": "🤍", "general": "🐾"}
# 본문용 단일 키워드 세트(loremflickr는 단일 키워드에서 안정적). 같은 단어도 lock으로 다른 사진.
BODY_KW = {
    "dog": ["dog", "puppy", "dog"], "cat": ["cat", "kitten", "cat"],
    "health": ["puppy", "dog", "pet"], "training": ["dog", "puppy", "dog"],
    "loss": ["dog", "puppy", "dog"], "general": ["pet", "dog", "cat"],
}
N_BODY_IMG = 3
_HDR = {"User-Agent": "Mozilla/5.0"}
_cache = {}


def fetch_img(keyword, lock, w=900, h=500):
    """토픽 이미지 base64 data URI (캐시)."""
    ck = (keyword, lock)
    if ck in _cache:
        return _cache[ck]
    uri = ""
    try:
        r = requests.get(f"https://loremflickr.com/{w}/{h}/{keyword}?lock={lock}",
                         headers=_HDR, timeout=25, allow_redirects=True)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            uri = "data:image/jpeg;base64," + base64.b64encode(r.content).decode("ascii")
            print(f"  이미지 [{keyword}#{lock}] {len(r.content)//1024}KB")
    except Exception as exc:  # noqa: BLE001
        print(f"  이미지 실패 [{keyword}]: {exc}")
    _cache[ck] = uri
    return uri


def body_images(cat, idx):
    kws = BODY_KW.get(cat, ["pet", "dog", "cat"])
    return [fetch_img(kws[k % len(kws)], idx * 10 + k + 1) for k in range(N_BODY_IMG)]


def ethics_badge(score):
    if score is None:
        return "#5F5E5A"
    return "#0F6E56" if score >= 90 else ("#854F0B" if score >= 70 else "#A32D2D")


# 전체 기사에 이미지 부착 + 발행/보류 분리
for i, a in enumerate(ART):
    a["_imgs"] = body_images(a.get("category", "general"), i)

published = [a for a in ART if a.get("ethics_passed", True)]
rejected = [a for a in ART if not a.get("ethics_passed", True)]
published.sort(key=lambda x: (x.get("pub_date", ""), x.get("ethics_score") or 0), reverse=True)

# 피드 포스트(서버 렌더) + 모달 데이터(JS)
posts = []
arts_data = []
for i, a in enumerate(published):
    cat = a.get("category", "general")
    color = CAT_COLOR.get(cat, "#5F5E5A")
    label = CAT_LABEL.get(cat, "소식")
    emoji = CAT_EMOJI.get(cat, "🐾")
    src = "레딧" if a.get("source_type") == "reddit" else "국내뉴스"
    e_color = ethics_badge(a.get("ethics_score"))
    hero = a["_imgs"][0] if a["_imgs"] else ""
    hero_html = (f'<img src="{hero}" alt="{html.escape(a.get("title",""))}">'
                 if hero else f'<div class="noimg" style="background:{color}"></div>')
    n_ang = len(a.get("deep_angles", []))
    posts.append(f"""
    <article class="post" onclick="openArt({i})" tabindex="0" role="button" aria-label="전문 보기: {html.escape(a.get('title',''))}">
      <div class="phead">
        <div class="avatar" style="background:{color}">{emoji}</div>
        <div class="pinfo">
          <div class="pname">RedCar Pet <span class="cat" style="color:{color}">· {label}</span></div>
          <div class="pmeta">{a.get('pub_date','')} · 심층 {n_ang}각도 · 출처 {src}</div>
        </div>
        <span class="epill" style="background:{e_color}">✓ 윤리 {a.get('ethics_score','-')}</span>
      </div>
      <h2 class="ptitle">{html.escape(a.get('title',''))}</h2>
      <p class="plead">{html.escape(a.get('lead',''))}</p>
      <div class="pimg">{hero_html}</div>
      <div class="pactions">
        <span class="act"><svg viewBox="0 0 24 24" class="ico"><path d="M7 10v11M2 13v6a1 1 0 001 1h3V10H3a1 1 0 00-1 1zm5 0 4.5-8a2 2 0 013.8 1.2L19 9h2.5a2 2 0 012 2.4l-1.5 7a2 2 0 01-2 1.6H7"/></svg>좋아요</span>
        <span class="act"><svg viewBox="0 0 24 24" class="ico"><path d="M21 11.5a8.4 8.4 0 01-9 8.4L3 21l1.1-3.3A8.4 8.4 0 1121 11.5z"/></svg>댓글</span>
        <span class="act"><svg viewBox="0 0 24 24" class="ico"><path d="M4 12v8a1 1 0 001 1h14a1 1 0 001-1v-8M16 6l-4-4-4 4M12 2v14"/></svg>공유</span>
        <span class="readmore">전문 보기 →</span>
      </div>
    </article>""")
    arts_data.append({
        "title": a.get("title", ""), "lead": a.get("lead", ""),
        "paragraphs": a.get("paragraphs", []), "images": a["_imgs"],
        "label": label, "color": color, "emoji": emoji,
        "date": a.get("pub_date", ""), "ethics": a.get("ethics_score"),
        "src": src, "angles": a.get("deep_angles", []),
    })

arts_js = json.dumps(arts_data, ensure_ascii=False)

rejected_html = ""
if rejected:
    rows = "".join(
        f'<li><b>{html.escape(r["title"])}</b> — 윤리 {r.get("ethics_score","?")}점, '
        f'위반 {", ".join(v.get("principle","") for v in r.get("ethics_violations",[]))}</li>'
        for r in rejected)
    rejected_html = f'<div class="held"><div class="held-h">⛔ 윤리 준칙 미달로 게재 보류 ({len(rejected)}건)</div><ul>{rows}</ul></div>'

avg = round(sum(a.get("ethics_score") or 0 for a in published) / max(len(published), 1))

HTML = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RedCar Pet — 반려동물 뉴스피드</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif; margin:0; background:#f0f2f5; color:#1c1e21; }}
  .topbar {{ position:sticky; top:0; z-index:10; background:#fff; border-bottom:1px solid #dadde1; padding:12px 16px; display:flex; align-items:center; justify-content:center; gap:10px; }}
  .topbar .logo {{ font-size:22px; font-weight:700; color:#c0392b; }}
  .topbar .tag {{ font-size:13px; color:#65676b; }}
  .feed {{ max-width:600px; margin:18px auto; padding:0 12px; display:flex; flex-direction:column; gap:16px; }}
  .post {{ background:#fff; border-radius:12px; box-shadow:0 1px 2px rgba(0,0,0,.1); padding:14px 16px 6px; cursor:pointer; transition:box-shadow .15s; }}
  .post:hover {{ box-shadow:0 3px 12px rgba(0,0,0,.15); }}
  .post:focus {{ outline:2px solid #c0392b; outline-offset:2px; }}
  .phead {{ display:flex; align-items:center; gap:10px; }}
  .avatar {{ width:42px; height:42px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:22px; flex:0 0 auto; }}
  .pinfo {{ flex:1; min-width:0; }}
  .pname {{ font-weight:600; font-size:15px; }}
  .pname .cat {{ font-weight:500; }}
  .pmeta {{ font-size:12px; color:#65676b; }}
  .epill {{ flex:0 0 auto; color:#fff; font-size:12px; padding:4px 9px; border-radius:14px; font-weight:500; }}
  .ptitle {{ font-size:19px; font-weight:700; line-height:1.35; margin:12px 0 6px; }}
  .plead {{ font-size:15px; color:#1c1e21; line-height:1.6; margin:0 0 12px; }}
  .pimg {{ margin:0 -16px; background:#e4e6eb; }}
  .pimg img {{ width:100%; display:block; max-height:360px; object-fit:cover; }}
  .pimg .noimg {{ width:100%; height:240px; }}
  .pactions {{ display:flex; align-items:center; gap:18px; border-top:1px solid #eceef0; margin-top:8px; padding:6px 2px; color:#65676b; font-size:14px; }}
  .act {{ display:inline-flex; align-items:center; gap:5px; }}
  .ico {{ width:18px; height:18px; fill:none; stroke:#65676b; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }}
  .readmore {{ margin-left:auto; color:#c0392b; font-weight:600; }}
  .held {{ max-width:600px; margin:18px auto; padding:14px 18px; background:#fbeeee; border:1px solid #f0d0d0; border-radius:12px; }}
  .held-h {{ color:#A32D2D; font-weight:600; margin-bottom:8px; }}
  .held ul {{ margin:0; padding-left:18px; color:#5a3a3a; font-size:14px; }}
  .held li {{ margin-bottom:5px; }}
  .overlay {{ position:fixed; inset:0; background:rgba(0,0,0,.6); display:none; align-items:flex-start; justify-content:center; padding:32px 14px; overflow-y:auto; z-index:100; }}
  .overlay.open {{ display:flex; }}
  .modal {{ background:#fff; max-width:680px; width:100%; border-radius:14px; overflow:hidden; }}
  .mband {{ height:8px; }}
  .minner {{ padding:24px 28px 32px; }}
  .mclose {{ float:right; cursor:pointer; font-size:22px; color:#999; border:none; background:none; }}
  .mtags {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; font-size:13px; align-items:center; }}
  .mtags .t {{ padding:3px 10px; border-radius:14px; color:#fff; }}
  .modal h2 {{ font-size:25px; line-height:1.35; margin:0 0 12px; }}
  .mlead {{ color:#c0392b; font-size:16px; font-weight:600; margin:0 0 18px; line-height:1.6; }}
  .mbody p {{ font-size:16px; line-height:1.85; color:#222; margin:0 0 16px; }}
  .mbody img {{ width:100%; border-radius:10px; margin:6px 0 18px; display:block; }}
  .angles {{ margin-top:18px; padding:14px 16px; background:#f0f2f5; border-radius:10px; font-size:13px; color:#444; line-height:1.7; }}
  @media (max-width:480px) {{ .minner {{ padding:18px; }} .modal h2 {{ font-size:21px; }} }}
</style></head>
<body>
<div class="topbar"><span class="logo">🐾 RedCar Pet</span><span class="tag">동물권 지향 뉴스피드 · 윤리 평균 {avg}점 · {len(published)}건</span></div>
<div class="feed">
{''.join(posts)}
</div>
{rejected_html}

<div class="overlay" id="overlay" onclick="if(event.target===this)closeArt()">
  <div class="modal" role="dialog" aria-modal="true">
    <div class="mband" id="m-band"></div>
    <div class="minner">
      <button class="mclose" onclick="closeArt()" aria-label="닫기">✕</button>
      <div class="mtags" id="m-tags"></div>
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
  // 본문 단락 사이에 이미지 분산 삽입
  const P = a.paragraphs || [], IM = (a.images||[]).filter(Boolean);
  let html = '';
  const slots = [];
  for(let k=0;k<IM.length;k++) slots.push(Math.round((k+1)*P.length/(IM.length+1))-1);
  for(let p=0;p<P.length;p++){{
    html += '<p>'+esc(P[p])+'</p>';
    const si = slots.indexOf(p);
    if(si>=0 && IM[si]) html += '<img src="'+IM[si]+'" alt="">';
  }}
  document.getElementById('m-body').innerHTML = html;
  document.getElementById('m-tags').innerHTML =
    '<span class="t" style="background:'+a.color+'">'+esc(a.emoji+' '+a.label)+'</span>'+
    '<span class="t" style="background:#1f1f1f">심층</span>'+
    '<span class="t" style="background:#0F6E56">✓ 윤리 준칙 '+(a.ethics??'-')+'</span>'+
    '<span style="color:#999">'+esc(a.date+' · 출처 '+a.src)+'</span>';
  document.getElementById('m-angles').innerHTML = a.angles && a.angles.length
    ? '<b>심층 확장 각도 '+a.angles.length+'개</b><br>'+a.angles.map(x=>'· '+esc(x)).join('<br>') : '';
  ov.classList.add('open'); document.body.style.overflow='hidden';
}}
function closeArt(){{ ov.classList.remove('open'); document.body.style.overflow=''; }}
document.addEventListener('keydown', e=>{{ if(e.key==='Escape') closeArt(); }});
</script>
</body></html>"""

open("output/web_sample.html", "w", encoding="utf-8").write(HTML)
print(f"SAVED | 피드 {len(published)}건(윤리 평균 {avg}), 보류 {len(rejected)}건, {len(HTML)} bytes")
