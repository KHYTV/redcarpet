# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""웹 게시 샘플 HTML 생성 (RedCar Pet — 뉴스/동영상 피드).

DB에서 기사(articles)와 동영상(videos)을 읽어 페이스북형 피드로 렌더링한다.
- 상단 검색 + 뉴스/동영상 탭 + 정렬(최신·조회수·좋아요·댓글)
- 기사 클릭 → 전문 모달(단락 사이 이미지), 동영상 클릭 → 임베드 재생
- 좋아요·댓글·조회수는 server.py API(SQLite)로 공유. 정적 호스팅 시 로컬 표시.
- 중앙일보 참고 타이포(Noto Sans KR, 본문 18px/1.9)
"""

import base64
import html
import json
import re

import requests

import db

ART = [a for a in db.get_all() if a.get("ethics_passed", True)]
VIDEOS = db.get_videos()

CAT_LABEL = {"dog": "반려견", "cat": "반려묘", "health": "건강", "training": "훈련",
             "loss": "반려동물 추모", "general": "소식"}
CAT_COLOR = {"dog": "#1D9E75", "cat": "#7F77DD", "health": "#378ADD", "training": "#BA7517",
             "loss": "#D4537E", "general": "#5F5E5A"}
CAT_EMOJI = {"dog": "🐶", "cat": "🐱", "health": "🩺", "training": "🦴", "loss": "🤍", "general": "🐾"}
BODY_KW = {"dog": ["dog", "puppy", "dog"], "cat": ["cat", "kitten", "cat"],
           "health": ["puppy", "dog", "pet"], "training": ["dog", "puppy", "dog"],
           "loss": ["dog", "puppy", "dog"], "general": ["pet", "dog", "cat"]}
N_BODY_IMG = 3
_HDR = {"User-Agent": "Mozilla/5.0"}
_cache = {}


def fetch_img(keyword, lock, w=900, h=500):
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


def article_images(a, idx):
    cat = a.get("category", "general")
    iks = [ik for ik in (a.get("image_keywords") or []) if (ik.get("kw") if isinstance(ik, dict) else ik)]
    default_kws = BODY_KW.get(cat, ["pet", "dog", "cat"])
    out = []
    for k in range(N_BODY_IMG):
        kw = ""
        if k < len(iks):
            raw = iks[k].get("kw") if isinstance(iks[k], dict) else iks[k]
            kw = (raw or "").strip().split()[0] if raw else ""
        uri = fetch_img(kw, idx * 10 + k + 1) if kw else ""
        if not uri:
            uri = fetch_img(default_kws[k % len(default_kws)], idx * 10 + k + 1)
        out.append(uri)
    return out


def _yt_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else ""


# 뉴스 데이터
ART.sort(key=lambda x: (x.get("pub_date", ""), x.get("ethics_score") or 0), reverse=True)
news_data = []
for i, a in enumerate(ART):
    imgs = article_images(a, i)
    cat = a.get("category", "general")
    news_data.append({
        "key": a.get("source_key", "") or ("t:" + a.get("title", "")),
        "title": a.get("title", ""), "lead": a.get("lead", ""),
        "paragraphs": a.get("paragraphs", []), "images": imgs, "hero": imgs[0] if imgs else "",
        "label": CAT_LABEL.get(cat, "소식"), "color": CAT_COLOR.get(cat, "#5F5E5A"),
        "emoji": CAT_EMOJI.get(cat, "🐾"), "date": a.get("pub_date", ""),
        "ethics": a.get("ethics_score"),
        "src": "레딧" if a.get("source_type") == "reddit" else "국내뉴스",
        "angles": a.get("deep_angles", []),
    })

# 동영상 데이터
videos_data = []
for v in VIDEOS:
    cat = v.get("category", "general")
    vid = _yt_id(v.get("url", ""))
    videos_data.append({
        "key": v.get("source_key", ""), "title": v.get("title", ""), "url": v.get("url", ""),
        "vid": vid, "thumb": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else "",
        "label": CAT_LABEL.get(cat, "소식"), "color": CAT_COLOR.get(cat, "#5F5E5A"),
        "emoji": CAT_EMOJI.get(cat, "🐾"), "date": v.get("pub_date", ""),
    })

news_js = json.dumps(news_data, ensure_ascii=False)
videos_js = json.dumps(videos_data, ensure_ascii=False)
comm_js = json.dumps(db.get_community(), ensure_ascii=False)  # 정적 페이지에도 보이도록 시드 임베드
avg = round(sum(a.get("ethics_score") or 0 for a in ART) / max(len(ART), 1))

HTML = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RedCar Pet — 반려동물 뉴스피드</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Noto Sans KR','Apple SD Gothic Neo','Malgun Gothic',Dotum,Arial,sans-serif; margin:0; background:#f0f2f5; color:#1c1e21; }}
  .topbar {{ position:sticky; top:0; z-index:10; background:#fff; border-bottom:1px solid #dadde1; padding:10px 16px; }}
  .toprow {{ display:flex; align-items:center; gap:12px; max-width:600px; margin:0 auto; flex-wrap:wrap; }}
  .logo {{ font-size:20px; font-weight:700; color:#c0392b; white-space:nowrap; }}
  .search {{ flex:1; min-width:140px; border:1px solid #dadde1; border-radius:20px; padding:8px 14px; font:inherit; background:#f0f2f5; }}
  .sortsel {{ border:1px solid #dadde1; border-radius:8px; padding:7px 8px; font:inherit; background:#fff; }}
  .tabs {{ display:flex; gap:6px; max-width:600px; margin:8px auto 0; }}
  .tab {{ flex:1; text-align:center; padding:8px; border:none; background:#f0f2f5; border-radius:8px; font:inherit; font-weight:600; color:#65676b; cursor:pointer; }}
  .tab.on {{ background:#c0392b; color:#fff; }}
  .feed {{ max-width:600px; margin:16px auto; padding:0 12px; display:flex; flex-direction:column; gap:16px; }}
  .post {{ background:#fff; border-radius:12px; box-shadow:0 1px 2px rgba(0,0,0,.1); padding:14px 16px 6px; cursor:pointer; }}
  .post:hover {{ box-shadow:0 3px 12px rgba(0,0,0,.15); }}
  .phead {{ display:flex; align-items:center; gap:10px; }}
  .avatar {{ width:42px; height:42px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:22px; flex:0 0 auto; }}
  .pinfo {{ flex:1; min-width:0; }} .pname {{ font-weight:600; font-size:15px; }} .pmeta {{ font-size:12px; color:#65676b; }}
  .aibadge {{ display:inline-block; background:#8B5BEE; color:#fff; font-size:11px; font-weight:600; padding:1px 7px; border-radius:10px; margin-left:6px; vertical-align:middle; }}
  .epill {{ flex:0 0 auto; color:#fff; font-size:12px; padding:4px 9px; border-radius:14px; font-weight:500; }}
  .ptitle {{ font-size:19px; font-weight:700; line-height:1.4; margin:12px 0 6px; letter-spacing:-0.3px; }}
  .plead {{ font-size:15px; color:#1c1e21; line-height:1.6; margin:0 0 12px; }}
  .pimg {{ margin:0 -16px; background:#e4e6eb; position:relative; }}
  .pimg img {{ width:100%; display:block; max-height:360px; object-fit:cover; }}
  .vthumb {{ aspect-ratio:16/9; background-size:cover; background-position:center; position:relative; display:flex; align-items:center; justify-content:center; }}
  .vplay {{ width:60px; height:60px; border-radius:50%; background:rgba(192,57,43,.92); color:#fff; display:flex; align-items:center; justify-content:center; font-size:26px; }}
  .pactions {{ display:flex; align-items:center; gap:16px; border-top:1px solid #eceef0; margin-top:8px; padding:7px 2px; color:#65676b; font-size:13px; }}
  .pactions b {{ color:#1c1e21; }}
  .likebtn {{ background:none; border:none; cursor:pointer; font:inherit; color:#65676b; padding:0; }}
  .likebtn:hover {{ color:#c0392b; }}
  .readmore {{ margin-left:auto; color:#c0392b; font-weight:600; }}
  .overlay {{ position:fixed; inset:0; background:rgba(0,0,0,.6); display:none; align-items:flex-start; justify-content:center; padding:32px 14px; overflow-y:auto; z-index:100; }}
  .overlay.open {{ display:flex; }}
  .modal {{ background:#fff; max-width:680px; width:100%; border-radius:14px; overflow:hidden; }}
  .mband {{ height:8px; }} .minner {{ padding:24px 28px 32px; }}
  .mclose {{ float:right; cursor:pointer; font-size:22px; color:#999; border:none; background:none; }}
  .mtags {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; font-size:13px; align-items:center; }}
  .mtags .t {{ padding:3px 10px; border-radius:14px; color:#fff; }}
  .modal h2 {{ font-size:28px; font-weight:700; line-height:1.4; margin:0 0 14px; letter-spacing:-0.3px; }}
  .mlead {{ color:#F6330A; font-size:18px; font-weight:500; margin:0 0 20px; line-height:1.7; }}
  .mbody p {{ font-size:18px; line-height:1.9; color:#222; margin:0 0 20px; }}
  .mbody img {{ width:100%; border-radius:10px; margin:6px 0 20px; display:block; }}
  .mbody iframe {{ width:100%; aspect-ratio:16/9; border:0; border-radius:10px; margin-bottom:16px; }}
  .angles {{ margin-top:20px; padding:14px 16px; background:#f5f5f5; border-radius:10px; font-size:14px; color:#444; line-height:1.8; }}
  .msns {{ margin-top:22px; border-top:1px solid #eceef0; padding-top:14px; }}
  .mlikebtn {{ background:#f0f2f5; border:none; border-radius:18px; padding:8px 16px; font:inherit; font-weight:600; color:#c0392b; cursor:pointer; }}
  .msns h4 {{ font-size:15px; margin:16px 0 10px; }}
  .cmt {{ background:#f0f2f5; border-radius:12px; padding:8px 12px; margin-bottom:8px; }}
  .cmt .cn {{ font-weight:600; font-size:13px; }} .cmt .ct {{ font-size:14px; margin-top:2px; }}
  .cform {{ display:flex; flex-direction:column; gap:8px; margin-top:10px; }}
  .cform input, .cform textarea {{ font:inherit; border:1px solid #dadde1; border-radius:8px; padding:8px 10px; width:100%; }}
  .cform textarea {{ min-height:60px; resize:vertical; }}
  .cform button {{ align-self:flex-end; background:#c0392b; color:#fff; border:none; border-radius:8px; padding:8px 18px; font:inherit; font-weight:600; cursor:pointer; }}
  .empty {{ text-align:center; color:#999; padding:40px 0; }}
  .writebox {{ background:#fff; border-radius:12px; box-shadow:0 1px 2px rgba(0,0,0,.1); padding:14px 16px; display:flex; flex-direction:column; gap:8px; }}
  .writebox input, .writebox textarea {{ font:inherit; border:1px solid #dadde1; border-radius:8px; padding:9px 11px; width:100%; }}
  .writebox textarea {{ min-height:70px; resize:vertical; }}
  .writebox .wbtn {{ align-self:flex-end; background:#c0392b; color:#fff; border:none; border-radius:8px; padding:8px 20px; font:inherit; font-weight:600; cursor:pointer; }}
  .ptext {{ font-size:15px; color:#1c1e21; line-height:1.7; margin:8px 0 12px; white-space:pre-wrap; }}
  @media (max-width:480px) {{ .minner {{ padding:18px; }} .modal h2 {{ font-size:23px; }} .mbody p {{ font-size:17px; }} }}
</style></head>
<body>
<div class="topbar">
  <div class="toprow">
    <span class="logo">🐾 RedCar Pet</span>
    <input id="search" class="search" placeholder="검색 (제목·내용)" oninput="onSearch(this.value)">
    <select id="sort" class="sortsel" onchange="onSort(this.value)">
      <option value="date">최신순</option>
      <option value="views">조회수순</option>
      <option value="likes">좋아요순</option>
      <option value="comments">댓글순</option>
    </select>
  </div>
  <div class="tabs">
    <button class="tab on" id="tab-news" onclick="setTab('news')">뉴스</button>
    <button class="tab" id="tab-video" onclick="setTab('video')">동영상</button>
    <button class="tab" id="tab-comm" onclick="setTab('comm')">커뮤니티</button>
  </div>
</div>
<div class="feed" id="feed"></div>

<div class="overlay" id="overlay" onclick="if(event.target===this)closeM()">
  <div class="modal" role="dialog" aria-modal="true">
    <div class="mband" id="m-band"></div>
    <div class="minner">
      <button class="mclose" onclick="closeM()" aria-label="닫기">✕</button>
      <div class="mtags" id="m-tags"></div>
      <h2 id="m-title"></h2>
      <p class="mlead" id="m-lead"></p>
      <div class="mbody" id="m-body"></div>
      <div class="angles" id="m-angles"></div>
      <div class="msns">
        <button class="mlikebtn" id="m-like">♥ 좋아요 <b id="m-lc">0</b></button>
        <h4>댓글 <span id="m-cc">0</span></h4>
        <div id="m-comments"></div>
        <div class="cform">
          <input id="m-name" placeholder="이름(선택)" maxlength="40">
          <textarea id="m-text" placeholder="댓글을 남겨보세요" maxlength="500"></textarea>
          <button id="m-send">댓글 등록</button>
        </div>
      </div>
    </div>
  </div>
</div>
<script>
const NEWS = {news_js}, VIDEOS = {videos_js};
let COMM = {comm_js};
let ENG = {{}}, tab = 'news', q = '', sortKey = 'date', curKey = null, curType = 'news';
const ov = document.getElementById('overlay');
function esc(s){{return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
function eng(k){{ return ENG[k] || (ENG[k]={{likes:0,comments:[],views:0}}); }}
function metric(x){{ const e=eng(x.key); return sortKey==='views'?e.views:sortKey==='likes'?e.likes:sortKey==='comments'?e.comments.length:0; }}

function curList(){{
  let list = (tab==='news'?NEWS:tab==='video'?VIDEOS:COMM).slice();
  if(q) list = list.filter(x => ((x.title||'')+' '+(x.lead||'')+' '+(x.text||'')).toLowerCase().includes(q));
  if(sortKey==='date') list.sort((a,b)=>((b.date||b.created_at||'')).localeCompare(a.date||a.created_at||''));
  else list.sort((a,b)=>metric(b)-metric(a));
  return list;
}}
function commCard(x){{
  const e=eng(x.key);
  const initial = (x.name||'익')[0];
  const badge = x.is_ai ? '<span class="aibadge">🤖 AI</span>' : '';
  return '<article class="post" onclick="openComm(\\''+x.key+'\\')">'+
    '<div class="phead"><div class="avatar" style="background:#8B5BEE">'+esc(initial)+'</div>'+
    '<div class="pinfo"><div class="pname">'+esc(x.name||'익명')+badge+'</div>'+
    '<div class="pmeta">'+esc((x.created_at||'').slice(0,16))+'</div></div></div>'+
    (x.title?'<h2 class="ptitle">'+esc(x.title)+'</h2>':'')+
    '<div class="ptext">'+esc((x.text||'').slice(0,200))+((x.text||'').length>200?'…':'')+'</div>'+
    '<div class="pactions"><button class="likebtn" onclick="event.stopPropagation();like(\\''+x.key+'\\')">♥ 좋아요 <b class="lc" data-k="'+x.key+'">'+e.likes+'</b></button>'+
    '<span>💬 <b class="cc" data-k="'+x.key+'">'+e.comments.length+'</b></span>'+
    '<span>👁 <b class="vc" data-k="'+x.key+'">'+e.views+'</b></span>'+
    '<span class="readmore">자세히 →</span></div></article>';
}}
function writeBox(){{
  return '<div class="writebox"><input id="w-name" placeholder="이름(선택)" maxlength="40">'+
    '<input id="w-title" placeholder="제목" maxlength="120">'+
    '<textarea id="w-text" placeholder="반려동물 이야기를 공유해보세요" maxlength="2000"></textarea>'+
    '<button class="wbtn" onclick="submitPost()">글 등록</button></div>';
}}
async function submitPost(){{
  const name=document.getElementById('w-name').value, title=document.getElementById('w-title').value.trim(), text=document.getElementById('w-text').value.trim();
  if(!title && !text){{ return; }}
  try{{
    const r=await(await fetch('/api/post',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name,title,text}})}})).json();
    if(r.post){{ COMM.unshift(r.post); render(); return; }}
  }}catch(e){{ COMM.unshift({{key:'local:'+Date.now(),name:name||'익명',title,text,created_at:''}}); render(); return; }}
}}
function openComm(key){{ const x=COMM.find(c=>c.key===key); if(!x)return; curKey=key; curType='comm'; track(key);
  document.getElementById('m-band').style.background='#8B5BEE';
  document.getElementById('m-title').textContent=x.title||'(제목 없음)';
  document.getElementById('m-lead').textContent='';
  document.getElementById('m-body').innerHTML='<p style="white-space:pre-wrap">'+esc(x.text||'')+'</p>';
  document.getElementById('m-tags').innerHTML='<span class="t" style="background:#8B5BEE">커뮤니티</span>'+(x.is_ai?'<span class="t" style="background:#8B5BEE">🤖 AI</span>':'')+'<span style="color:#999">'+esc(x.name||'익명')+' · '+esc((x.created_at||'').slice(0,16))+'</span>';
  document.getElementById('m-angles').innerHTML='';
  document.getElementById('m-lc').textContent=eng(key).likes; renderComments(key);
  ov.classList.add('open'); document.body.style.overflow='hidden'; }}
function newsCard(x){{
  const e=eng(x.key);
  const hero = x.hero ? '<img src="'+x.hero+'" alt="">' : '';
  return '<article class="post" onclick="openArt(\\''+x.key+'\\')">'+
    '<div class="phead"><div class="avatar" style="background:'+x.color+'">'+x.emoji+'</div>'+
    '<div class="pinfo"><div class="pname">RedCar Pet · '+esc(x.label)+'</div>'+
    '<div class="pmeta">'+esc(x.date)+' · 출처 '+esc(x.src)+'</div></div>'+
    '<span class="epill" style="background:#0F6E56">✓ 윤리 '+(x.ethics??'-')+'</span></div>'+
    '<h2 class="ptitle">'+esc(x.title)+'</h2><p class="plead">'+esc(x.lead)+'</p>'+
    '<div class="pimg">'+hero+'</div>'+
    '<div class="pactions"><button class="likebtn" onclick="event.stopPropagation();like(\\''+x.key+'\\')">♥ 좋아요 <b class="lc" data-k="'+x.key+'">'+e.likes+'</b></button>'+
    '<span>💬 <b class="cc" data-k="'+x.key+'">'+e.comments.length+'</b></span>'+
    '<span>👁 <b class="vc" data-k="'+x.key+'">'+e.views+'</b></span>'+
    '<span class="readmore">전문 보기 →</span></div></article>';
}}
function videoCard(x){{
  const e=eng(x.key);
  const thumb = x.thumb ? 'style="background-image:url('+x.thumb+')"' : 'style="background:'+x.color+'"';
  return '<article class="post" onclick="openVideo(\\''+x.key+'\\')">'+
    '<div class="phead"><div class="avatar" style="background:'+x.color+'">'+x.emoji+'</div>'+
    '<div class="pinfo"><div class="pname">RedCar Pet · '+esc(x.label)+' · 동영상</div>'+
    '<div class="pmeta">'+esc(x.date)+'</div></div></div>'+
    '<h2 class="ptitle">'+esc(x.title)+'</h2>'+
    '<div class="pimg"><div class="vthumb" '+thumb+'><div class="vplay">▶</div></div></div>'+
    '<div class="pactions"><button class="likebtn" onclick="event.stopPropagation();like(\\''+x.key+'\\')">♥ 좋아요 <b class="lc" data-k="'+x.key+'">'+e.likes+'</b></button>'+
    '<span>💬 <b class="cc" data-k="'+x.key+'">'+e.comments.length+'</b></span>'+
    '<span>👁 <b class="vc" data-k="'+x.key+'">'+e.views+'</b></span>'+
    '<span class="readmore">재생 →</span></div></article>';
}}
function render(){{
  const list = curList();
  const feed = document.getElementById('feed');
  const card = tab==='news'?newsCard:tab==='video'?videoCard:commCard;
  const head = (tab==='comm') ? writeBox() : '';
  const body = list.length ? list.map(card).join('')
    : '<div class="empty">'+(tab==='video'?'아직 동영상이 없습니다.':tab==='comm'?'첫 글을 남겨보세요.':'검색 결과가 없습니다.')+'</div>';
  feed.innerHTML = head + body;
}}
function setTab(t){{ tab=t;
  for(const id of ['news','video','comm']) document.getElementById('tab-'+id).classList.toggle('on', t===id);
  render(); }}
function onSearch(v){{ q=(v||'').toLowerCase().trim(); render(); }}
function onSort(v){{ sortKey=v; render(); }}

function setCount(cls,key,val){{ document.querySelectorAll('.'+cls+'[data-k="'+key+'"]').forEach(x=>x.textContent=val); }}
async function track(key){{ try{{ const r=await(await fetch('/api/view',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{key}})}})).json(); if(r.views!=null){{eng(key).views=r.views; setCount('vc',key,r.views);}} }}catch(e){{ eng(key).views++; setCount('vc',key,eng(key).views); }} }}
async function like(key){{ try{{ const r=await(await fetch('/api/like',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{key}})}})).json(); if(r.likes!=null){{eng(key).likes=r.likes; setCount('lc',key,r.likes); if(curKey===key)document.getElementById('m-lc').textContent=r.likes;}} }}catch(e){{ eng(key).likes++; setCount('lc',key,eng(key).likes); if(curKey===key)document.getElementById('m-lc').textContent=eng(key).likes; }} }}
function renderComments(key){{ const cs=eng(key).comments||[]; document.getElementById('m-cc').textContent=cs.length;
  document.getElementById('m-comments').innerHTML = cs.map(c=>'<div class="cmt"><div class="cn">'+esc(c.name)+'</div><div class="ct">'+esc(c.text)+'</div></div>').join('')||'<div style="color:#999;font-size:14px;">첫 댓글을 남겨보세요.</div>'; }}
async function sendComment(){{ const key=curKey; if(!key)return; const name=document.getElementById('m-name').value, text=document.getElementById('m-text').value.trim(); if(!text)return;
  try{{ const r=await(await fetch('/api/comment',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{key,name,text}})}})).json(); if(r.comment){{eng(key).comments.push(r.comment);}} }}
  catch(e){{ eng(key).comments.push({{name:name||'익명',text}}); }}
  document.getElementById('m-text').value=''; renderComments(key); setCount('cc',key,eng(key).comments.length); }}

function openArt(key){{ const x=NEWS.find(n=>n.key===key); if(!x)return; curKey=key; curType='news'; track(key);
  document.getElementById('m-band').style.background=x.color;
  document.getElementById('m-title').textContent=x.title;
  document.getElementById('m-lead').textContent=x.lead;
  const P=x.paragraphs||[], IM=(x.images||[]).filter(Boolean); let h=''; const slots=[];
  for(let k=0;k<IM.length;k++) slots.push(Math.round((k+1)*P.length/(IM.length+1))-1);
  for(let p=0;p<P.length;p++){{ h+='<p>'+esc(P[p])+'</p>'; const si=slots.indexOf(p); if(si>=0&&IM[si]) h+='<img src="'+IM[si]+'">'; }}
  document.getElementById('m-body').innerHTML=h;
  document.getElementById('m-tags').innerHTML='<span class="t" style="background:'+x.color+'">'+esc(x.emoji+' '+x.label)+'</span><span class="t" style="background:#1f1f1f">심층</span><span class="t" style="background:#0F6E56">✓ 윤리 '+(x.ethics??'-')+'</span><span style="color:#999">'+esc(x.date+' · 출처 '+x.src)+'</span>';
  document.getElementById('m-angles').innerHTML = x.angles&&x.angles.length?'<b>심층 확장 각도 '+x.angles.length+'개</b><br>'+x.angles.map(a=>'· '+esc(a)).join('<br>'):'';
  document.getElementById('m-lc').textContent=eng(key).likes; renderComments(key);
  ov.classList.add('open'); document.body.style.overflow='hidden'; }}
function openVideo(key){{ const x=VIDEOS.find(v=>v.key===key); if(!x)return; curKey=key; curType='video'; track(key);
  document.getElementById('m-band').style.background=x.color;
  document.getElementById('m-title').textContent=x.title;
  document.getElementById('m-lead').textContent='';
  document.getElementById('m-body').innerHTML = x.vid?'<iframe src="https://www.youtube.com/embed/'+x.vid+'" allowfullscreen></iframe>':'<p><a href="'+x.url+'" target="_blank">영상 보기 →</a></p>';
  document.getElementById('m-tags').innerHTML='<span class="t" style="background:'+x.color+'">'+esc(x.emoji+' '+x.label)+'</span><span class="t" style="background:#1f1f1f">동영상</span><span style="color:#999">'+esc(x.date)+'</span>';
  document.getElementById('m-angles').innerHTML='';
  document.getElementById('m-lc').textContent=eng(key).likes; renderComments(key);
  ov.classList.add('open'); document.body.style.overflow='hidden'; }}
function closeM(){{ ov.classList.remove('open'); document.body.style.overflow=''; curKey=null; }}
document.getElementById('m-like').onclick=()=>{{ if(curKey)like(curKey); }};
document.getElementById('m-send').onclick=sendComment;
document.addEventListener('keydown',e=>{{ if(e.key==='Escape')closeM(); }});
async function loadEng(){{
  try{{ ENG=await(await fetch('/api/engagement')).json()||{{}}; }}catch(e){{ ENG={{}}; }}
  try{{ const c=await(await fetch('/api/community')).json(); if(c&&c.posts&&c.posts.length) COMM=c.posts; }}catch(e){{}}
  render();
}}
loadEng();
</script>
</body></html>"""

import os as _os
open("output/web_sample.html", "w", encoding="utf-8").write(HTML)
_os.makedirs("docs", exist_ok=True)
open("docs/index.html", "w", encoding="utf-8").write(HTML)
print(f"SAVED | 뉴스 {len(ART)}건, 동영상 {len(VIDEOS)}건, {len(HTML)} bytes → output + docs/index.html")
