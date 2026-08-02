"""The cockpit's markup, styles and behaviour.

Kept out of the builder so the builder stays about data. The page works with or
without the rendered page images beside it: when `pages/` is present it shows
the real exam pages, and when it is not it falls back to extracted text, so the
same HTML serves both the full bundle and the standalone file.

Everything is inline. No bundler, no framework, no CDN, no web fonts. State
lives in localStorage under the `ck:` prefix and is migrated forward, never
wiped - there is real progress in there.
"""

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Graduation cockpit</title>
<style>
:root{
  --bg:#faf9f7; --panel:#fff; --sunk:#f3f0ec; --fg:#1a1917; --dim:#645f58; --faint:#8a847b;
  --line:#e6e1db; --line2:#efebe6; --accent:#9c4221; --accent-soft:#f7ece5;
  --warn:#8f1d1d; --warn-soft:#fbeaea; --ok:#1b6238; --ok-soft:#e7f3ec;
  --hl:#fdeec2; --shadow:0 1px 2px rgba(20,16,12,.05);
  --s1:4px; --s2:8px; --s3:12px; --s4:18px; --s5:28px; --s6:44px; --r:14px;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#121110; --panel:#1c1b19; --sunk:#161513; --fg:#f0ede8; --dim:#a8a29a; --faint:#847e75;
  --line:#2e2b28; --line2:#232120; --accent:#f0956a; --accent-soft:#2c211b;
  --warn:#f08b8b; --warn-soft:#301d1d; --ok:#7fd0a5; --ok-soft:#15291f;
  --hl:#4a3b18; --shadow:0 1px 2px rgba(0,0,0,.35);
}}
:root[data-theme=dark]{
  --bg:#121110; --panel:#1c1b19; --sunk:#161513; --fg:#f0ede8; --dim:#a8a29a; --faint:#847e75;
  --line:#2e2b28; --line2:#232120; --accent:#f0956a; --accent-soft:#2c211b;
  --warn:#f08b8b; --warn-soft:#301d1d; --ok:#7fd0a5; --ok-soft:#15291f;
  --hl:#4a3b18; --shadow:0 1px 2px rgba(0,0,0,.35);
}
:root[data-theme=light]{
  --bg:#faf9f7; --panel:#fff; --sunk:#f3f0ec; --fg:#1a1917; --dim:#645f58; --faint:#8a847b;
  --line:#e6e1db; --line2:#efebe6; --accent:#9c4221; --accent-soft:#f7ece5;
  --warn:#8f1d1d; --warn-soft:#fbeaea; --ok:#1b6238; --ok-soft:#e7f3ec;
  --hl:#fdeec2; --shadow:0 1px 2px rgba(20,16,12,.05);
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--fg);
  font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-text-size-adjust:100%;overflow-wrap:break-word}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
/* The main region is focused programmatically after a route change so screen
   readers land in the new content; it must not draw a ring around the page. */
#main:focus,#main:focus-visible{outline:none}
@media(prefers-reduced-motion:no-preference){
  .fade{animation:fade .18s ease-out}
  @keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
}
/* shell */
.top{position:sticky;top:0;z-index:40;background:color-mix(in srgb,var(--bg) 90%,transparent);
  backdrop-filter:saturate(1.5) blur(10px);border-bottom:1px solid var(--line)}
.top-in{max-width:1120px;margin:0 auto;padding:10px var(--s4);display:flex;gap:var(--s2);align-items:center}
.brand{font-weight:680;letter-spacing:-.015em;font-size:1rem;white-space:nowrap}
.brand i{color:var(--faint);font-weight:400;font-style:normal;font-size:.76rem;margin-left:var(--s2)}
.grow{flex:1}
.ico{border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:10px;
  min-width:38px;height:38px;display:grid;place-items:center;cursor:pointer;font-size:.9rem;flex:none;padding:0 10px}
.ico:hover{border-color:var(--accent);color:var(--accent)}
.shell{max-width:1120px;margin:0 auto;padding:0 var(--s4) 100px;display:flex;gap:var(--s5)}
.rail{display:none;flex:0 0 172px;position:sticky;top:66px;align-self:flex-start;padding-top:var(--s4)}
.rail button{display:flex;gap:10px;align-items:center;width:100%;text-align:left;border:0;background:none;
  color:var(--dim);font:inherit;font-size:.9rem;padding:9px 11px;border-radius:10px;cursor:pointer}
.rail button:hover{background:var(--line2);color:var(--fg)}
.rail button[aria-current=page]{background:var(--accent-soft);color:var(--accent);font-weight:640}
.main{flex:1;min-width:0;padding-top:var(--s4)}
.tabs{position:fixed;left:0;right:0;bottom:0;z-index:40;display:flex;
  background:color-mix(in srgb,var(--bg) 94%,transparent);backdrop-filter:blur(10px);
  border-top:1px solid var(--line);padding:6px 2px calc(6px + env(safe-area-inset-bottom))}
.tabs button{flex:1;border:0;background:none;color:var(--faint);font:inherit;font-size:.64rem;
  display:flex;flex-direction:column;align-items:center;gap:2px;padding:6px 2px;cursor:pointer;min-height:48px}
.tabs button b{font-size:1.05rem;font-weight:400;line-height:1}
.tabs button[aria-current=page]{color:var(--accent)}
@media(min-width:880px){.rail{display:block}.tabs{display:none}.shell{padding-bottom:var(--s6)}}
/* type */
h1{font-size:1.55rem;margin:0 0 var(--s3);letter-spacing:-.025em;line-height:1.2}
h2{font-size:1rem;margin:var(--s5) 0 var(--s2);letter-spacing:-.01em}
h3{font-size:.92rem;margin:var(--s4) 0 var(--s1)}
.kicker{font-size:.67rem;text-transform:uppercase;letter-spacing:.1em;color:var(--faint);font-weight:660;margin-bottom:var(--s2)}
.dim{color:var(--dim)}.faint{color:var(--faint)}
.sm{font-size:.85rem}.xs{font-size:.76rem}
.num{font-size:3.1rem;font-weight:700;line-height:.95;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
/* surfaces */
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
  padding:var(--s4);margin:var(--s3) 0;box-shadow:var(--shadow)}
.card.tight{padding:var(--s3)}
.plain{border:0;box-shadow:none;background:none;padding:0}
.row{display:flex;justify-content:space-between;gap:var(--s3);align-items:baseline;flex-wrap:wrap}
.hero{background:linear-gradient(160deg,var(--accent-soft),var(--panel) 70%);border-color:color-mix(in srgb,var(--accent) 22%,var(--line))}
.gate{background:var(--warn-soft);border-left:3px solid var(--warn);padding:11px 14px;
  border-radius:0 10px 10px 0;font-size:.87rem;margin:var(--s3) 0}
.note{background:var(--accent-soft);border-left:3px solid var(--accent);padding:11px 14px;
  border-radius:0 10px 10px 0;font-size:.87rem;margin:var(--s3) 0}
.banner{position:sticky;top:58px;z-index:30;border-radius:10px;padding:11px 14px;margin:var(--s3) 0;
  display:flex;gap:var(--s3);align-items:center;font-size:.88rem;border:1px solid}
.banner.warn{background:var(--accent-soft);border-color:color-mix(in srgb,var(--accent) 40%,transparent);color:var(--accent)}
.banner.crit{background:var(--warn-soft);border-color:color-mix(in srgb,var(--warn) 55%,transparent);color:var(--warn);font-weight:620}
.pill{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:99px;
  border:1px solid var(--line);font-size:.73rem;color:var(--dim);margin:0 5px 5px 0;white-space:nowrap}
.pill.a{border-color:color-mix(in srgb,var(--accent) 42%,transparent);color:var(--accent);background:var(--accent-soft)}
.pill.g{border-color:color-mix(in srgb,var(--ok) 42%,transparent);color:var(--ok);background:var(--ok-soft)}
.pill.r{border-color:color-mix(in srgb,var(--warn) 45%,transparent);color:var(--warn);background:var(--warn-soft)}
.bar{height:6px;background:var(--line);border-radius:99px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--accent);border-radius:99px}
.grid{display:grid;gap:var(--s3)}
@media(min-width:640px){.grid.two{grid-template-columns:1fr 1fr}.grid.three{grid-template-columns:repeat(3,1fr)}}
/* controls */
button.act,select,input[type=search],input[type=text],input[type=number]{font:inherit;font-size:.88rem;
  padding:9px 13px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--fg);
  min-height:40px}
button.act{cursor:pointer}
button.act:hover{border-color:var(--accent);color:var(--accent)}
button.act.on{background:var(--accent);border-color:var(--accent);color:#fff}
button.act.wide{width:100%;justify-content:center}
.bigbtn{display:block;width:100%;text-align:center;background:var(--accent);color:#fff;border:0;
  border-radius:12px;padding:14px;font:inherit;font-weight:640;font-size:.95rem;cursor:pointer;min-height:50px}
input[type=search],input[type=text]{width:100%}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:var(--s3) 0}
/* tables */
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:.86rem}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line2);vertical-align:top}
th{color:var(--faint);font-weight:640;font-size:.7rem;text-transform:uppercase;letter-spacing:.07em}
tr.past td{opacity:.4}
blockquote{margin:var(--s2) 0;padding:12px 15px;background:var(--sunk);border:1px solid var(--line2);
  border-radius:10px;font-size:.89rem;white-space:pre-wrap}
blockquote.ans{border-left:3px solid var(--ok)}
mark{background:var(--hl);color:inherit;padding:0 2px;border-radius:3px}
label.chk{display:flex;gap:11px;align-items:flex-start;cursor:pointer;padding:7px 0;min-height:40px}
input[type=checkbox]{margin-top:4px;flex:none;width:19px;height:19px;accent-color:var(--accent)}
.empty{text-align:center;color:var(--faint);padding:var(--s6) var(--s4);font-size:.9rem}
.back{border:0;background:none;color:var(--accent);font:inherit;font-size:.85rem;cursor:pointer;padding:6px 0}
/* today blocks */
.block{display:flex;gap:var(--s3);align-items:flex-start;padding:11px 13px;border-radius:11px;
  border:1px solid var(--line);margin:var(--s2) 0;background:var(--panel)}
.block.rev{background:var(--sunk);border-style:dashed}
.block .h{margin-left:auto;font-variant-numeric:tabular-nums;color:var(--dim);font-size:.84rem;white-space:nowrap}
/* rings */
.ring{--p:0;width:44px;height:44px;border-radius:50%;flex:none;
  background:conic-gradient(var(--accent) calc(var(--p)*1%),var(--line) 0);
  display:grid;place-items:center;font-size:.66rem;font-weight:660;color:var(--dim)}
.ring>span{width:34px;height:34px;border-radius:50%;background:var(--panel);display:grid;place-items:center}
/* heatmap */
.heat{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;max-width:420px}
.heat b{font-size:.6rem;color:var(--faint);text-align:center;font-weight:600}
.heat i{aspect-ratio:1;border-radius:5px;background:var(--line2);display:grid;place-items:center;
  font-size:.6rem;font-style:normal;color:var(--faint);cursor:default}
.heat i.ex{outline:2px solid var(--warn);font-weight:700;color:var(--warn)}
/* paper viewer */
.thumbs{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-top:var(--s3)}
.thumb{border:1px solid var(--line);border-radius:9px;overflow:hidden;background:#fff;cursor:zoom-in;
  aspect-ratio:1/1.41;position:relative;padding:0}
.thumb img{width:100%;height:100%;object-fit:cover;object-position:top;display:block}
.thumb b{position:absolute;left:6px;bottom:6px;background:rgba(0,0,0,.65);color:#fff;
  font-size:.63rem;font-weight:500;padding:1px 7px;border-radius:99px}
.lb{position:fixed;inset:0;z-index:90;background:rgba(10,9,8,.96);display:none;flex-direction:column;overscroll-behavior:contain}
.lb.on{display:flex}
.lb-bar{display:flex;align-items:center;gap:var(--s2);padding:10px 14px;color:#eee;font-size:.83rem;flex:none;
  padding-top:calc(10px + env(safe-area-inset-top))}
.lb-bar button{border:1px solid #4a4640;background:#242220;color:#eee;border-radius:9px;
  padding:9px 13px;font:inherit;font-size:.83rem;cursor:pointer;min-height:40px}
.lb-body{flex:1;overflow:auto;display:flex;align-items:flex-start;justify-content:center;
  padding:0 var(--s2) var(--s5);touch-action:pinch-zoom pan-x pan-y}
.lb-body img{max-width:100%;height:auto;border-radius:6px;background:#fff}
.lb-body.zoom img{max-width:none;width:200%}
.lb-body.split{gap:10px}
.lb-body.split img{max-width:49%}
/* drill */
.opt{display:block;width:100%;text-align:left;padding:11px 14px;margin:6px 0;border:1px solid var(--line);
  border-radius:10px;font:inherit;font-size:.88rem;background:var(--panel);color:var(--fg);cursor:pointer;min-height:44px}
.opt:hover{border-color:var(--accent)}
.opt.right{border-color:var(--ok);background:var(--ok-soft);color:var(--ok)}
.opt.wrong{border-color:var(--warn);background:var(--warn-soft);color:var(--warn)}
.rate{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:var(--s3)}
.rate button{padding:11px 4px;font-size:.82rem;min-height:46px}
.rate button.g0:hover{border-color:var(--warn);color:var(--warn)}
.rate button.g3:hover{border-color:var(--ok);color:var(--ok)}
details>summary{cursor:pointer;font-weight:620;font-size:.88rem;list-style:none;padding:5px 0;min-height:32px}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"▸ ";color:var(--faint)}
details[open]>summary::before{content:"▾ "}
.md h1,.md h2,.md h3{font-size:.93rem;margin:1.1em 0 .3em}
.md ul,.md ol{padding-left:20px;margin:.4em 0}
.md li{margin:.3em 0;font-size:.89rem}
.md p{font-size:.89rem;margin:.5em 0}
.md code{background:var(--line2);padding:1px 5px;border-radius:5px;font-size:.85em}
/* palette */
.pal{position:fixed;inset:0;z-index:95;background:rgba(10,9,8,.4);display:none;
  align-items:flex-start;justify-content:center;padding-top:12vh}
.pal.on{display:flex}
.pal-box{background:var(--panel);border:1px solid var(--line);border-radius:14px;width:min(620px,92vw);
  box-shadow:0 20px 60px rgba(0,0,0,.28);overflow:hidden}
.pal-box input{border:0;border-bottom:1px solid var(--line);border-radius:0;font-size:1rem;padding:15px 18px}
.pal-list{max-height:52vh;overflow:auto}
.pal-list button{display:block;width:100%;text-align:left;border:0;background:none;color:var(--fg);
  font:inherit;font-size:.88rem;padding:11px 18px;cursor:pointer;border-bottom:1px solid var(--line2)}
.pal-list button:hover,.pal-list button[aria-selected=true]{background:var(--accent-soft);color:var(--accent)}
.pal-list .t{font-size:.7rem;color:var(--faint);text-transform:uppercase;letter-spacing:.07em}
/* print */
.printonly{display:none}
@media print{
  .top,.rail,.tabs,.lb,.pal,.noprint{display:none!important}
  .shell{display:block;padding:0;max-width:none}
  .main{padding:0}
  body{background:#fff;color:#000;font-size:11pt}
  .printonly{display:block}
  .examcard{page-break-after:always;break-after:page;border:1px solid #000;border-radius:0;
    padding:14mm;box-shadow:none;margin:0}
  .examcard:last-child{page-break-after:auto}
  .card{box-shadow:none}
}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
</style></head><body>

<header class="top"><div class="top-in">
  <div class="brand">Cockpit <i id="stat"></i></div>
  <div class="grow"></div>
  <button class="ico" id="go-pal" title="Command palette (Ctrl+K)" aria-label="Command palette">⌘K</button>
  <button class="ico" id="go-theme" title="Theme" aria-label="Toggle theme">◐</button>
</div></header>

<div class="shell">
  <nav class="rail" id="rail" aria-label="Sections"></nav>
  <main class="main" id="main" tabindex="-1"></main>
</div>

<nav class="tabs" id="tabs" aria-label="Sections"></nav>

<div class="lb" id="lb" role="dialog" aria-modal="true" aria-label="Paper viewer">
  <div class="lb-bar">
    <button id="lb-close">✕</button>
    <button id="lb-prev">‹</button>
    <span id="lb-label" class="grow" style="text-align:center"></span>
    <button id="lb-next">›</button>
    <button id="lb-zoom">Zoom</button>
    <button id="lb-split" class="noshow">Key</button>
  </div>
  <div class="lb-body" id="lb-body"><img id="lb-img" alt="Exam page"></div>
</div>

<div class="pal" id="pal" role="dialog" aria-modal="true" aria-label="Command palette">
  <div class="pal-box">
    <input type="text" id="pal-q" placeholder="Jump to a course, paper, topic or question…" autocomplete="off">
    <div class="pal-list" id="pal-list" role="listbox"></div>
  </div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
"use strict";
const D=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const store={
  get(k,d){try{const v=localStorage.getItem('ck:'+k);return v==null?d:JSON.parse(v)}catch(e){return d}},
  set(k,v){try{localStorage.setItem('ck:'+k,JSON.stringify(v));return true}catch(e){return false}},
  keys(){try{return Object.keys(localStorage).filter(k=>k.startsWith('ck:'))}catch(e){return []}}
};
const today=()=>new Date().toISOString().slice(0,10);
const iso=d=>d.toISOString().slice(0,10);
const dayDiff=(a,b)=>Math.round((new Date(a+'T00:00:00')-new Date(b+'T00:00:00'))/864e5);
const addDays=(a,n)=>iso(new Date(new Date(a+'T00:00:00').getTime()+n*864e5));
const cname=c=>(D.names[c]||(D.lib[c]&&D.lib[c].name)||c);
const plural=(n,w)=>n+' '+w+(n===1?'':'s');
const examOf=c=>D.exams.find(e=>e.code===c)||D.winter.find(w=>w.code===c)||null;
const qOf=(c,i)=>((D.lib[c]||{}).questions||[])[i];

/* ---------- migration: never wipe, only move forward ---------- */
(function migrate(){
  if(store.get('v',0)>=2) return;
  // v1 stored a flat list of "worked it" indices against clustered cards.
  // Those indices no longer address the same thing, but the fact that a course
  // had progress is worth keeping, so it becomes a Good grade on that course's
  // first N cards rather than being thrown away.
  Object.keys(D.drill||{}).forEach(code=>{
    const old=store.get('drilled:'+code,null);
    if(!Array.isArray(old)||!old.length) return;
    const g=store.get('grade:'+code,{});
    (D.drill[code]||[]).slice(0,old.length).forEach(card=>{
      if(g[card.q]===undefined) g[card.q]={e:2.5,i:1,due:today(),r:1,l:0};
    });
    store.set('grade:'+code,g);
  });
  store.set('v',2);
})();

/* ---------- spaced repetition (SM-2, trimmed) ---------- */
const GRADES=[['Again',0],['Hard',1],['Good',2],['Easy',3]];
function gradeCard(code,q,g){
  const all=store.get('grade:'+code,{});
  const s=all[q]||{e:2.5,i:0,due:today(),r:0,l:0};
  if(g===0){ s.e=Math.max(1.3,s.e-0.2); s.i=0; s.l++; }
  else if(g===1){ s.e=Math.max(1.3,s.e-0.15); s.i=Math.max(1,Math.round(s.i*1.2)||1); }
  else if(g===2){ s.i=s.i?Math.round(s.i*s.e):1; }
  else { s.e=s.e+0.15; s.i=Math.max(2,Math.round((s.i||1)*s.e*1.3)); }
  s.r++; s.last=today(); s.due=addDays(today(),s.i);
  all[q]=s; store.set('grade:'+code,all);
  if(g===0) logMiss(code,q);
  return s;
}
function logMiss(code,q){
  const question=qOf(code,q); if(!question) return;
  const log=store.get('misses',[]);
  log.push({c:code,t:question.topic,d:today(),q});
  store.set('misses',log.slice(-800));
}
function dueQueue(code){
  const all=store.get('grade:'+code,{}), t=today();
  const cards=(D.drill[code]||[]).slice();
  const seen=c=>all[c.q];
  // Overdue first, then never-seen by how often the question recurs, then the
  // rest by due date. What you keep missing surfaces without being asked for.
  return cards.sort((a,b)=>{
    const A=seen(a),B=seen(b);
    if(A&&B) return dayDiff(t,A.due)-dayDiff(t,B.due)||b.seen-a.seen;
    if(A&&!B) return dayDiff(t,A.due)>=0?-1:1;
    if(!A&&B) return dayDiff(t,B.due)>=0?1:-1;
    return b.seen-a.seen||(a.keyed?-1:1);
  });
}
function recallOf(code){
  const all=store.get('grade:'+code,{}), total=(D.drill[code]||[]).length;
  const vals=Object.values(all);
  if(!total) return null;
  const strong=vals.filter(s=>s.i>=4).length;
  return {seen:vals.length,total,coverage:vals.length/total,
          recall:vals.length?strong/vals.length:0,
          score:total?(strong/total):0};
}
function weakTopics(code,limit){
  const log=store.get('misses',[]).filter(m=>!code||m.c===code);
  const by={};
  log.forEach(m=>{by[m.t]=(by[m.t]||0)+1});
  return Object.entries(by).sort((a,b)=>b[1]-a[1]).slice(0,limit||5);
}

/* ---------- planned vs actual ---------- */
const plannedFor=d=>(D.calendar[d]||[]).reduce((a,s)=>a+s[1],0);
function loggedFor(d){return store.get('logged:'+d,null)}
function debtToDate(){
  const t=today(); let owed=0,done=0;
  Object.keys(D.calendar).filter(d=>d<t).forEach(d=>{
    owed+=plannedFor(d); const l=loggedFor(d); done+=(l==null?plannedFor(d):l);
  });
  return {owed:Math.round(owed*10)/10,done:Math.round(done*10)/10,debt:Math.round((owed-done)*10)/10};
}
function reflow(){
  /* Redistribute the shortfall over the days that are left.
     This is deliberately a redistribution, not a re-solve: the real scheduler
     lives in the generator and has constraints (5-day contact, consolidation
     windows) this cannot see. Review touches are never scaled - they are the
     part that keeps courses warm - so only learning blocks move. */
  const t=today(), debt=debtToDate().debt;
  if(debt<=0) return null;
  const future=Object.keys(D.calendar).filter(d=>d>=t).sort();
  const capacity=d=>D.exams.some(e=>e.date===d)?4:7;
  const room=future.map(d=>Math.max(0,capacity(d)-plannedFor(d)));
  const spare=room.reduce((a,b)=>a+b,0);
  const plan=[];
  let left=debt;
  future.forEach((d,i)=>{
    if(left<=0||spare<=0) return;
    const add=Math.min(room[i],Math.round((debt*room[i]/spare)*4)/4);
    if(add>0){plan.push([d,add]);left-=add;}
  });
  return {debt,spare:Math.round(spare*10)/10,plan,unplaced:Math.round(left*10)/10};
}

/* ---------- theme ---------- */
const applyTheme=t=>t?document.documentElement.setAttribute('data-theme',t)
                     :document.documentElement.removeAttribute('data-theme');
applyTheme(store.get('theme',null));
$('#go-theme').onclick=()=>{const c=store.get('theme',null);
  const n=c==='dark'?'light':c==='light'?null:'dark'; store.set('theme',n); applyTheme(n);};

/* ---------- routing ---------- */
const VIEWS=[['home','Today','◈'],['courses','Courses','▤'],['drill','Drill','◇'],
             ['quiz','Quiz','✓'],['plan','Plan','▦'],['cards','Cards','▣'],['more','More','⋯']];
let route={view:'home',course:null,tab:'method',paper:null};
$('#rail').innerHTML=VIEWS.map(([id,l,ic])=>
  `<button data-v="${id}"><span aria-hidden="true">${ic}</span> ${l}</button>`).join('');
$('#tabs').innerHTML=VIEWS.map(([id,l,ic])=>
  `<button data-v="${id}"><b aria-hidden="true">${ic}</b>${l}</button>`).join('');
$$('#rail button,#tabs button').forEach(b=>b.onclick=()=>go(b.dataset.v));
$('#go-pal').onclick=openPal;

function go(view,opts={}){
  route={view,course:opts.course??null,tab:opts.tab??'method',paper:opts.paper??null};
  $$('#rail button,#tabs button').forEach(b=>
    b.setAttribute('aria-current',b.dataset.v===view?'page':'false'));
  render(); window.scrollTo(0,0); $('#main').focus({preventScroll:true});
}
document.addEventListener('keydown',e=>{
  if($('#lb').classList.contains('on')){
    if(e.key==='Escape')closeLb();
    if(e.key==='ArrowRight')$('#lb-next').click();
    if(e.key==='ArrowLeft')$('#lb-prev').click();
    return;
  }
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openPal();return;}
  if($('#pal').classList.contains('on')){ palKey(e); return; }
  if(e.target.matches('input,textarea,select'))return;
  if(e.key==='/'){e.preventDefault();openPal();}
});

/* ---------- markdown ---------- */
function md(src){
  const out=[];let table=false;
  for(let ln of String(src).split('\n')){
    if(/^\|/.test(ln)){
      if(/^\|[\s\-:|]+\|$/.test(ln))continue;
      const cells=ln.split('|').slice(1,-1).map(c=>`<td>${fmt(c.trim())}</td>`).join('');
      if(!table){out.push('<div class="scroll"><table>');table=true;}
      out.push('<tr>'+cells+'</tr>');continue;
    }
    if(table){out.push('</table></div>');table=false;}
    if(/^#{1,3}\s/.test(ln))out.push('<h3>'+fmt(ln.replace(/^#+\s/,''))+'</h3>');
    else if(/^\d+\.\s/.test(ln))out.push('<li class="ol">'+fmt(ln.replace(/^\d+\.\s/,''))+'</li>');
    else if(/^[-*]\s/.test(ln))out.push('<li>'+fmt(ln.replace(/^[-*]\s/,''))+'</li>');
    else if(!ln.trim())out.push('');
    else out.push('<p>'+fmt(ln)+'</p>');
  }
  if(table)out.push('</table></div>');
  return out.join('\n')
    .replace(/(<li class="ol">[\s\S]*?<\/li>\n?)+/g,m=>'<ol>'+m.replace(/ class="ol"/g,'')+'</ol>')
    .replace(/(<li>(?!\s*class)[\s\S]*?<\/li>\n?)+/g,m=>m.includes('<ol>')?m:'<ul>'+m+'</ul>');
}
const fmt=s=>esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<code>$1</code>');

/* ---------- lightbox ---------- */
let lbSet=[],lbAt=0,lbName='',lbKey=null;
function openLb(files,at,name,keyFiles){
  lbSet=files;lbAt=at;lbName=name;lbKey=keyFiles||null;
  $('#lb').classList.add('on'); $('#lb-body').classList.remove('zoom','split');
  $('#lb-split').style.display=lbKey?'':'none';
  showLb();
}
function showLb(){
  const b=$('#lb-body');
  b.innerHTML=`<img id="lb-img" alt="Page ${lbAt+1}" src="${D.pagesDir}${lbSet[lbAt]}">`+
    (b.classList.contains('split')&&lbKey&&lbKey[lbAt]?`<img alt="Key" src="${D.pagesDir}${lbKey[lbAt]}">`:'');
  $('#lb-label').textContent=`${lbName} — ${lbAt+1} / ${lbSet.length}`;
  b.scrollTop=0;
  // Preload the neighbours so paging feels instant.
  [lbAt+1,lbAt-1].forEach(i=>{if(lbSet[i]){const im=new Image();im.src=D.pagesDir+lbSet[i];}});
}
function closeLb(){$('#lb').classList.remove('on');$('#lb-body').innerHTML='';}
$('#lb-close').onclick=closeLb;
$('#lb-prev').onclick=()=>{if(lbAt>0){lbAt--;showLb();}};
$('#lb-next').onclick=()=>{if(lbAt<lbSet.length-1){lbAt++;showLb();}};
$('#lb-zoom').onclick=()=>{$('#lb-body').classList.toggle('zoom');};
$('#lb-split').onclick=()=>{$('#lb-body').classList.toggle('split');showLb();};
(function swipe(){
  let x0=null;
  const b=$('#lb-body');
  b.addEventListener('touchstart',e=>{if(e.touches.length===1)x0=e.touches[0].clientX},{passive:true});
  b.addEventListener('touchend',e=>{
    if(x0==null)return; const dx=e.changedTouches[0].clientX-x0; x0=null;
    if(Math.abs(dx)<60)return;
    dx<0?$('#lb-next').click():$('#lb-prev').click();
  },{passive:true});
})();

function pageBlock(code,docIndex){
  const files=D.pages[code+':'+docIndex];
  if(!files||!files.length) return '';
  return `<div class="thumbs">`+files.map((f,i)=>
    `<button class="thumb" data-pg="${code}:${docIndex}" data-at="${i}" aria-label="Page ${i+1}">
       <img loading="lazy" src="${D.pagesDir}${f}" alt=""><b>${i+1}</b></button>`).join('')+`</div>`;
}
function bindThumbs(root){
  root.querySelectorAll('.thumb').forEach(t=>t.onclick=()=>{
    const [c,i]=t.dataset.pg.split(':');
    const doc=(D.lib[c].documents||[]).find(d=>d.i==i);
    openLb(D.pages[t.dataset.pg],+t.dataset.at,doc?doc.name:cname(c));
  });
}

/* ---------- views ---------- */
function deadlineBanner(){
  const t=today();
  const soon=D.exams.filter(e=>e.book_by>=t).map(e=>({e,d:dayDiff(e.book_by,t)}))
    .filter(x=>x.d<=7).sort((a,b)=>a.d-b.d);
  if(!soon.length) return '';
  const crit=soon.filter(x=>x.d<=2);
  const list=soon.map(x=>`${esc(x.e.name)} (${x.d===0?'today':x.d+'d'})`).join(' · ');
  if(crit.length) return `<div class="banner crit" role="alert">⚠ BOOKING CLOSES: ${list}. Miss it and the exam is gone.</div>`;
  return `<div class="banner warn">Booking closes within a week: ${list}</div>`;
}

function viewHome(){
  const t=today();
  const upcoming=D.exams.filter(e=>e.date>=t).sort((a,b)=>a.date<b.date?-1:1);
  const n=upcoming[0];
  const slots=D.calendar[t]||[];
  const done=store.get('done:'+t,[]);
  let h=deadlineBanner();

  if(n){
    const d=dayDiff(n.date,t);
    h+=`<section class="card hero fade">
      <div class="kicker">next exam</div>
      <div class="row" style="align-items:flex-start">
        <div><div class="num">${d===0?'today':d}</div>
          <div class="sm dim" style="margin-top:2px">${d===0?'':plural(d,'day')+' away'}</div></div>
        <div style="text-align:right">
          <div style="font-weight:660;font-size:1.05rem">${esc(n.name)}</div>
          <div class="sm dim">${n.date}</div>
          <div class="pill ${n.campus==='Pavia'?'':'r'}" style="margin-top:6px">📍 ${esc(n.campus)}</div>
        </div>
      </div>
      <div class="gate"><b>Pass gate.</b> ${esc(n.gate)}</div>
      <button class="bigbtn" data-start="${n.code}">Start now → drill ${esc(cname(n.code))}</button>
      <div class="chips"><button class="act" data-open="${n.code}">Open course</button>
        <button class="act" data-card="${n.code}">Exam card</button></div>
    </section>`;
  } else h+='<div class="card empty">No exams ahead.</div>';

  h+='<h2>Today&rsquo;s plan</h2>';
  if(!slots.length) h+='<div class="card empty">Nothing scheduled today.</div>';
  else{
    const total=slots.reduce((a,s)=>a+s[1],0);
    h+=`<div class="card"><div class="row"><span class="kicker" style="margin:0">${total} h planned</span>
      <span class="xs faint">dashed = spaced review</span></div>`+
      slots.map((s,i)=>`<label class="block ${s[2]==='review'?'rev':''}">
        <input type="checkbox" data-done="${i}" ${done.includes(i)?'checked':''}>
        <span><b>${esc(cname(s[0]))}</b>
          <span class="xs faint" style="display:block">${s[2]==='review'?'spaced review — retrieval, not re-reading':'new material'}</span></span>
        <span class="h">${s[1]} h</span></label>`).join('')+
      `<div class="chips"><button class="act" data-log="1">Log actual hours</button></div></div>`;
  }

  const weak=weakTopics(null,4);
  if(weak.length){
    h+='<h2>Your weakest topics</h2><div class="card tight">'+
      weak.map(([topic,n])=>`<div class="row" style="padding:5px 0">
        <span class="sm">${esc(topic)}</span><span class="pill r">${plural(n,'miss')}</span></div>`).join('')+
      '</div>';
  }

  const debt=debtToDate();
  if(debt.debt>0.5){
    h+=`<div class="note"><b>${debt.debt} h behind.</b> Planned ${debt.owed} h to date, logged ${debt.done} h.
      <button class="act" data-reflow="1" style="margin-top:8px">Re-flow the remaining days</button></div>`;
  }
  return h;
}

function ringFor(code){
  const r=recallOf(code);
  if(!r) return '';
  const p=Math.round(r.score*100);
  return `<div class="ring" style="--p:${p}" title="coverage x recall"><span>${p}%</span></div>`;
}

function viewCourses(){
  const card=(e,winter)=>{
    const lib=D.lib[e.code]||{documents:[],questions:[]};
    const papers=lib.documents.filter(d=>d.role==='paper').length;
    const keys=(lib.questions||[]).filter(q=>q.answer).length;
    const cd=D.exams.find(x=>x.code===e.code)?dayDiff(e.date,today()):null;
    return `<div class="card" role="button" tabindex="0" data-open="${e.code}" style="cursor:pointer">
      <div class="row" style="align-items:center">
        <div style="min-width:0">
          <div style="font-weight:640">${esc(e.name)}</div>
          <div class="xs faint" style="margin-top:2px">
            ${winter?'January / February':e.date+' · '+esc(e.campus)}</div>
        </div>
        ${ringFor(e.code)}
      </div>
      <div style="margin-top:9px">
        ${cd!=null&&cd>=0?`<span class="pill ${cd<=7?'r':'a'}">${cd===0?'today':plural(cd,'day')}</span>`:''}
        <span class="pill">${e.cfu} CFU</span><span class="pill">${e.hours} h</span>
        ${papers?`<span class="pill">${plural(papers,'paper')}</span>`:'<span class="pill r">no papers</span>'}
        ${keys?`<span class="pill g">${keys} keyed</span>`:''}
        <span class="pill">${(lib.questions||[]).length} questions</span>
      </div></div>`;
  };
  return '<h1>Courses</h1><div class="kicker">September</div>'+
    D.exams.slice().sort((a,b)=>a.date<b.date?-1:1).map(e=>card(e,false)).join('')+
    '<div class="kicker" style="margin-top:26px">January / February</div>'+
    D.winter.map(w=>card(w,true)).join('')+
    '<div class="card tight sm faint">Winter dates are not published — Esse3 returns nothing for 2027.</div>';
}

function viewCourse(code){
  const e=examOf(code)||{name:cname(code),cfu:'',hours:'',gate:''};
  const cd=D.exams.find(x=>x.code===code)?dayDiff(e.date,today()):null;
  const tabs=[['method','Method'],['papers','Papers'],['drill','Drill'],
              ['topics','Topics'],['questions','Questions'],['files','Files']];
  let h=`<button class="back" data-back="1">← All courses</button>
    <h1 style="margin-top:6px">${esc(e.name)}</h1>
    <div style="margin-bottom:2px">
      ${cd!=null&&cd>=0?`<span class="pill ${cd<=7?'r':'a'}">${cd===0?'today':plural(cd,'day')}</span>`:''}
      ${e.date?`<span class="pill">${e.date}</span><span class="pill ${e.campus==='Pavia'?'':'r'}">📍 ${esc(e.campus)}</span>`
              :'<span class="pill">Jan/Feb</span>'}
      ${e.cfu?`<span class="pill">${e.cfu} CFU</span>`:''}${e.hours?`<span class="pill">${e.hours} h</span>`:''}
      ${e.book_by?`<span class="pill r">book by ${e.book_by}</span>`:''}
    </div>`;
  if(e.gate) h+=`<div class="gate"><b>Pass gate.</b> ${esc(e.gate)}</div>`;
  if(e.note) h+=`<div class="note">${esc(e.note)}</div>`;
  h+='<div class="chips">'+tabs.map(([id,l])=>
      `<button class="act ${route.tab===id?'on':''}" data-tab="${id}">${l}</button>`).join('')+
    (D.exams.find(x=>x.code===code)?`<button class="act" data-card="${code}">Exam card</button>`:'')+
    '</div><div id="ctab" class="fade"></div>';
  return h;
}

function courseTab(code){
  const lib=D.lib[code]||{documents:[],questions:[]};
  if(route.tab==='method'){
    const pack=D.packs[code];
    return pack?`<div class="card md">${md(pack)}</div>`:'<div class="card empty">No study pack.</div>';
  }
  if(route.tab==='papers') return papersTab(code);
  if(route.tab==='drill') return drillTab(code);
  if(route.tab==='topics') return topicsTab(code);
  if(route.tab==='questions'){
    const qs=lib.questions||[];
    if(!qs.length) return '<div class="card empty">No questions extracted.</div>';
    const topics=[...new Set(qs.map(q=>q.topic))].sort();
    const f=store.get('qf:'+code,'');
    return `<div class="card tight"><select id="qtopic" aria-label="Filter by topic">
        <option value="">All topics (${qs.length})</option>
        ${topics.map(t=>`<option ${f===t?'selected':''}>${esc(t)}</option>`).join('')}
      </select></div><div id="qlist"></div>`;
  }
  const order={paper:0,solution:1,material:2,'image-only':3,stub:4};
  return (lib.documents||[]).slice()
    .sort((a,b)=>(order[a.role]-order[b.role])||b.chars-a.chars)
    .map(d=>`<details class="card"><summary>${esc(d.name)}</summary>
      <div style="margin:8px 0"><span class="pill ${d.role==='paper'?'a':d.role==='solution'?'g':d.role==='stub'?'r':''}">${d.role}</span>
        <span class="pill">${d.kind}</span><span class="pill">${d.chars.toLocaleString()} chars</span></div>
      ${pageBlock(code,d.i)}
      ${d.chars?`<blockquote>${esc(d.text.slice(0,14000))}</blockquote>`
        :`<div class="sm faint">No text layer. On disk:<br><code>${esc(d.path||'')}</code></div>`}
    </details>`).join('');
}

function papersTab(code){
  const papers=(D.papers[code]||[]);
  const docs=(D.lib[code].documents||[]).filter(d=>(d.role==='paper'||d.role==='solution')&&(D.pages[code+':'+d.i]||d.chars));
  if(!papers.length&&!docs.length) return '<div class="card empty">No exam papers archived.</div>';
  let h=`<div class="sm dim" style="margin:12px 0">${plural(papers.length,'sittable paper')} · timed mode hides the answers and starts a clock</div>`;
  h+=papers.map((p,i)=>`<div class="card"><div class="row">
      <b>${esc(p.name)}</b>
      <span>${p.keyed?`<span class="pill g">${p.keyed} keyed</span>`:'<span class="pill">no key</span>'}
        <span class="pill">${plural(p.qs.length,'question')}</span></span></div>
    ${p.doc!=null?pageBlock(code,p.doc):''}
    <div class="chips"><button class="act" data-sit="${i}">Sit this paper timed</button></div></div>`).join('');
  const extra=docs.filter(d=>!papers.some(p=>p.name===d.name));
  if(extra.length) h+='<h2>Other documents</h2>'+extra.map(d=>
    `<details class="card"><summary>${esc(d.name)}</summary>${pageBlock(code,d.i)}
      ${d.chars?`<blockquote>${esc(d.text.slice(0,12000))}</blockquote>`:''}</details>`).join('');
  return h;
}

function sitPaper(code,index){
  const p=(D.papers[code]||[])[index]; if(!p) return '';
  const key='sit:'+code+':'+index;
  const st=store.get(key,{start:null,reveal:false});
  const qs=p.qs.map(i=>qOf(code,i));
  const mins=st.start?Math.floor((Date.now()-st.start)/60000):0;
  let h=`<button class="back" data-back-paper="1">← Papers</button>
    <h1 style="margin-top:6px">${esc(p.name)}</h1>
    <div class="card"><div class="row">
      <span class="kicker" style="margin:0">${st.start?`running · ${mins} min`:'not started'}</span>
      <span>${plural(qs.length,'question')}</span></div>
      <div class="chips">
        ${st.start?'':`<button class="act on" data-sit-start="${index}">Start the clock</button>`}
        ${st.start&&!st.reveal?`<button class="act" data-sit-reveal="${index}">Reveal the key</button>`:''}
        ${st.start?`<button class="act" data-sit-reset="${index}">Reset</button>`:''}
      </div></div>`;
  if(p.doc!=null) h+=`<div class="card">${pageBlock(code,p.doc)}</div>`;
  h+=qs.map((q,i)=>`<div class="card"><div>
      <span class="pill a">${esc(q.topic)}</span>${q.marks?`<span class="pill">${q.marks} marks</span>`:''}
      <span class="pill">Q${i+1}</span></div>
      <blockquote>${esc(q.text)}</blockquote>
      ${q.answer?(st.reveal?`<blockquote class="ans">${esc(q.answer)}</blockquote>`
        :'<div class="xs faint">Key hidden until you reveal.</div>')
        :'<div class="xs faint">No published key — self-assess.</div>'}
    </div>`).join('');
  return h;
}

function drillTab(code){
  const queue=dueQueue(code);
  if(!queue.length) return '<div class="card empty">No cards for this course.</div>';
  const all=store.get('grade:'+code,{});
  const t=today();
  const due=queue.filter(c=>!all[c.q]||dayDiff(t,all[c.q].due)>=0).length;
  const r=recallOf(code);
  const pos=Math.min(store.get('pos:'+code,0),queue.length-1);
  const card=queue[pos], question=qOf(code,card.q);
  const state=all[card.q];
  return `<div class="card tight"><div class="row">
      <span class="kicker" style="margin:0">${due} due · ${queue.length} total</span>
      ${r?`<span class="xs faint">${Math.round(r.coverage*100)}% seen · ${Math.round(r.recall*100)}% strong</span>`:''}</div>
      <div class="bar" style="margin-top:8px"><i style="width:${r?Math.round(r.score*100):0}%"></i></div></div>
    <div class="card fade"><div>
      <span class="pill a">${esc(question.topic)}</span>
      ${card.seen>1?`<span class="pill">${plural(card.seen,'paper')}${card.share?` · ${Math.round(card.share*100)}%`:''}</span>`:''}
      ${question.marks?`<span class="pill">${question.marks} marks</span>`:''}
      ${card.keyed?'<span class="pill g">answer published</span>':'<span class="pill r">no key — self-assess</span>'}
      ${state?`<span class="pill">seen ${state.r}×</span>`:'<span class="pill">new</span>'}</div>
      <blockquote>${esc(question.text)}</blockquote>
      ${question.answer?`<details><summary>Show worked answer</summary>
        <blockquote class="ans">${esc(question.answer)}</blockquote></details>`:''}
      <div class="xs faint" style="margin-top:6px">${esc(question.paper)}</div>
      <div class="rate">${GRADES.map(([label,g])=>
        `<button class="act g${g}" data-grade="${g}" data-q="${card.q}">${label}</button>`).join('')}</div>
    </div>
    <div class="chips"><button class="act" data-skip="1">Skip</button>
      <button class="act" data-resetq="1">Reset this course</button></div>`;
}

function topicsTab(code){
  const topics=D.topics[code]||[];
  if(!topics.length) return '<div class="card empty">No topic data.</div>';
  const max=topics[0].n;
  const weak=Object.fromEntries(weakTopics(code,50));
  return `<div class="sm dim" style="margin:12px 0">What recurs across the archived papers, most frequent first.</div>`+
    topics.map(t=>`<div class="card tight">
      <div class="row"><b class="sm">${esc(t.topic)}</b>
        <span class="xs faint">${t.n} q · ${Math.round(t.share*100)}%${t.keyed?` · ${t.keyed} keyed`:''}
        ${weak[t.topic]?` · <span style="color:var(--warn)">${weak[t.topic]} missed</span>`:''}</span></div>
      <div class="bar" style="margin-top:7px"><i style="width:${Math.round(100*t.n/max)}%"></i></div></div>`).join('');
}

function qList(code,filter){
  const qs=(D.lib[code].questions||[]).filter(q=>!filter||q.topic===filter);
  return `<div class="sm dim" style="margin:12px 0">${plural(qs.length,'question')}</div>`+
    qs.map(q=>`<div class="card"><div>
      <span class="pill a">${esc(q.topic)}</span>
      ${q.marks?`<span class="pill">${q.marks} marks</span>`:''}
      ${q.mcq?'<span class="pill">multiple choice</span>':''}
      ${q.answer?'<span class="pill g">answer published</span>':'<span class="pill r">no key</span>'}</div>
      <blockquote>${esc(q.text)}</blockquote>
      ${q.answer?`<details><summary>Show worked answer</summary>
        <blockquote class="ans">${esc(q.answer)}</blockquote></details>`:''}
      <div class="xs faint">${esc(q.paper)}</div></div>`).join('');
}

function viewDrill(){
  const codes=Object.keys(D.drill).sort((a,b)=>{
    const A=D.exams.find(e=>e.code===a),B=D.exams.find(e=>e.code===b);
    return (A?dayDiff(A.date,today()):999)-(B?dayDiff(B.date,today()):999);});
  if(!codes.length) return '<div class="card empty">No cards.</div>';
  const cur=codes.includes(store.get('drillCourse'))?store.get('drillCourse'):codes[0];
  return `<h1>Drill</h1><div class="card tight"><select id="dpick" aria-label="Course">
      ${codes.map(c=>`<option value="${c}" ${c===cur?'selected':''}>${esc(cname(c))} (${D.drill[c].length})</option>`).join('')}
    </select></div><div id="dbody">${drillTab(cur)}</div>`;
}

function viewQuiz(){
  const banks=Object.keys(D.quiz);
  if(!banks.length) return '<div class="card empty">No quiz bank.</div>';
  const b=banks[0], bank=D.quiz[b], st=store.get('quiz:'+b,{});
  const answered=Object.keys(st).length, right=Object.values(st).filter(Boolean).length;
  return `<h1>Quiz</h1>
    <div class="card tight"><div class="row"><b>${esc(bank.name)}</b>
      <span class="sm dim">${bank.items.length} questions</span></div>
      <div class="xs faint" style="margin-top:3px">${esc(bank.source)}</div>
      <div class="bar" style="margin-top:9px"><i style="width:${Math.round(100*answered/bank.items.length)}%"></i></div>
      <div class="row" style="margin-top:8px"><span class="sm dim">${answered} answered · ${right} correct
        ${answered?`(${Math.round(100*right/answered)}%)`:''}</span>
      <button class="act" id="zreset">Reset</button></div></div>
    <div id="zlist">${quizItems(b)}</div>`;
}
function quizItems(b){
  const bank=D.quiz[b], st=store.get('quiz:'+b,{});
  return bank.items.map((q,i)=>{
    const shown=st[i]!==undefined;
    return `<div class="card"><div><span class="pill a">${esc(q.topic)}</span>
      ${q.n?`<span class="pill">#${q.n}</span>`:''}
      ${shown?(st[i]?'<span class="pill g">correct</span>':'<span class="pill r">wrong</span>'):''}</div>
      <div style="margin:9px 0 5px;font-size:.92rem">${esc(q.stem)}</div>
      ${q.options.map((o,j)=>`<button class="opt ${shown?(o.correct?'right':'wrong'):''}"
        data-z="${i}" data-o="${j}" ${shown?'disabled':''}>${esc(o.letter)}. ${esc(o.text)}${shown&&o.correct?' ✓':''}</button>`).join('')}
    </div>`;}).join('');
}

function viewPlan(){
  const t=today();
  const dates=Object.keys(D.calendar).sort();
  const examOn=d=>D.exams.find(e=>e.date===d);
  const load=d=>(D.calendar[d]||[]).reduce((a,s)=>a+s[1],0);
  const max=Math.max(...dates.map(load),1);
  const first=new Date(dates[0]+'T00:00:00');
  const pad=(first.getDay()+6)%7;
  let cells='';
  for(let i=0;i<pad;i++) cells+='<i></i>';
  dates.forEach(d=>{
    const l=load(d), ex=examOn(d);
    const op=l?(0.18+0.82*l/max).toFixed(2):0;
    cells+=`<i class="${ex?'ex':''}" title="${d} — ${l} h${ex?' — EXAM '+ex.name:''}"
      style="${l?`background:color-mix(in srgb,var(--accent) ${Math.round(op*100)}%,var(--line2))`:''}">${
      ex?'✱':(l?d.slice(8):'')}</i>`;
  });
  let h=`<h1>Plan</h1>
    <div class="card"><div class="kicker">eight weeks · ✱ = exam · darker = heavier</div>
      <div class="heat">${['M','T','W','T','F','S','S'].map(x=>`<b>${x}</b>`).join('')}${cells}</div></div>`;
  h+='<h2>September</h2><div class="card scroll"><table><caption class="sr">September exams</caption>'+
    '<tr><th>Date</th><th>Course</th><th>Campus</th><th>Book by</th><th>h</th><th>CFU</th></tr>'+
    D.exams.map(e=>`<tr class="${e.date<t?'past':''}"><td>${e.date.slice(5)}</td><td>${esc(e.name)}</td>
      <td>${esc(e.campus)}</td><td>${e.book_by.slice(5)}</td><td>${e.hours}</td><td>${e.cfu}</td></tr>`).join('')+
    '</table></div>';
  h+='<h2>Full calendar</h2><div class="card scroll"><table><tr><th>Date</th><th>h</th><th>Work</th></tr>'+
    dates.map(d=>{
      const ex=examOn(d);
      const w=(D.calendar[d]||[]).map(s=>
        `${esc(cname(s[0]))} <span class="faint">${s[1]}h${s[2]==='review'?' ®':''}</span>`).join(', ')||'—';
      return `<tr class="${d<t?'past':''}"><td>${d.slice(5)}</td><td>${load(d)||''}</td>
        <td>${ex?`<b style="color:var(--warn)">EXAM · ${esc(ex.name)}</b><br>`:''}${w}</td></tr>`;
    }).join('')+'</table></div><div class="xs faint">® = spaced review</div>';
  return h;
}

function viewCards(){
  return '<h1 class="noprint">Exam cards</h1>'+
    '<div class="card tight noprint sm dim">One page per exam when printed. Everything that loses marks when forgotten.'+
    ' <button class="act" onclick="window.print()" style="margin-left:8px">Print</button></div>'+
    D.exams.map(e=>{
      const traps=(D.traps&&D.traps[e.code])||[];
      return `<section class="card examcard">
        <div class="kicker">exam card</div>
        <h2 style="margin:2px 0 10px;font-size:1.25rem">${esc(e.name)}</h2>
        <table><tr><th>Date</th><td><b>${e.date}</b></td></tr>
          <tr><th>Campus</th><td><b>${esc(e.campus)}</b></td></tr>
          <tr><th>Book by</th><td><b>${e.book_by}</b> — miss it and the exam is gone</td></tr>
          <tr><th>Weight</th><td>${e.cfu} CFU · ${e.hours} h budgeted</td></tr></table>
        <h3>Pass gate</h3><div class="gate">${esc(e.gate)}</div>
        ${traps.length?`<h3>Scoring traps</h3><ul>${traps.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
      </section>`;}).join('');
}

function viewMore(){
  const debt=debtToDate();
  const sc=D.scenarios||{};
  const cur=sc._current||{};
  let h='<h1>More</h1>';
  h+=`<h2>Progress</h2><div class="card">
    <div class="row"><span class="sm">Planned to date</span><b>${debt.owed} h</b></div>
    <div class="row"><span class="sm">Logged</span><b>${debt.done} h</b></div>
    <div class="row"><span class="sm">Balance</span>
      <b style="color:${debt.debt>0.5?'var(--warn)':'var(--ok)'}">${debt.debt>0?'−':''}${Math.abs(debt.debt)} h</b></div>
    <div class="chips"><button class="act" data-log="1">Log hours for a day</button>
      <button class="act" data-reflow="1">Re-flow remaining days</button></div></div>`;

  h+=`<h2>What if I defer one exam to winter?</h2>
    <div class="card tight sm dim">Each row re-runs the real scheduler without that exam.
      Current plan: ${cur.slack!=null?cur.slack+' h slack':'—'}, worst gap ${cur.worst_gap||'—'} days.</div>
    <div class="card scroll"><table><tr><th>Defer</th><th>Frees</th><th>CFU</th><th>Slack after</th><th>Days over 7 h</th></tr>`+
    D.exams.map(e=>{const s=sc[e.code]; if(!s||!s.feasible) return '';
      const gain=cur.slack!=null?(s.slack-cur.slack).toFixed(1):'';
      return `<tr><td>${esc(e.name)}</td><td>${s.freed_hours} h</td><td>${s.freed_cfu}</td>
        <td><b>${s.slack} h</b>${gain?` <span class="faint">(+${gain})</span>`:''}</td>
        <td>${s.overrun_days}</td></tr>`;}).join('')+
    '</table></div><div class="xs faint">Deferring anything pushes it into a winter session whose dates are not yet published.</div>';

  h+=`<h2>Daily digest</h2><div class="card"><div id="digest"></div>
    <div class="chips"><button class="act" data-digest="1">Refresh</button></div></div>`;

  h+=`<h2>Backup</h2><div class="card">
    <div class="sm dim">localStorage on one browser is a single point of failure eight weeks before graduation.</div>
    <div class="chips"><button class="act" data-export="1">Export progress (JSON)</button>
      <button class="act" data-import="1">Import</button></div>
    <textarea id="io" class="noprint" style="display:none;width:100%;height:150px;font:12px ui-monospace,monospace;
      border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--sunk);color:var(--fg)"></textarea></div>`;
  return h;
}

function digestText(){
  const t=today(), slots=D.calendar[t]||[];
  const n=D.exams.filter(e=>e.date>=t).sort((a,b)=>a.date<b.date?-1:1)[0];
  const weak=weakTopics(null,3).map(([x])=>x);
  const book=D.exams.filter(e=>e.book_by>=t&&dayDiff(e.book_by,t)<=7);
  return [
    `${t} — ${slots.reduce((a,s)=>a+s[1],0)} h planned`,
    n?`Next: ${n.name} in ${dayDiff(n.date,t)} d at ${n.campus} (${n.date})`:'No exams ahead',
    ...slots.map(s=>`  ${s[2]==='review'?'®':'•'} ${cname(s[0])} ${s[1]}h`),
    book.length?`Booking closes: ${book.map(e=>e.name+' '+e.book_by).join('; ')}`:'',
    weak.length?`Weakest: ${weak.join(', ')}`:'',
  ].filter(Boolean).join('\n');
}

/* ---------- command palette ---------- */
let palItems=[],palAt=0;
function buildPal(){
  const out=[];
  D.exams.concat(D.winter).forEach(e=>out.push({t:'course',l:e.name,s:e.date||'Jan/Feb',go:()=>go('courses',{course:e.code})}));
  Object.keys(D.papers||{}).forEach(c=>(D.papers[c]||[]).forEach((p,i)=>
    out.push({t:'paper',l:p.name,s:cname(c),go:()=>go('courses',{course:c,tab:'papers',paper:i})})));
  Object.keys(D.topics||{}).forEach(c=>(D.topics[c]||[]).forEach(t=>
    out.push({t:'topic',l:t.topic,s:cname(c)+' · '+t.n,go:()=>go('courses',{course:c,tab:'topics'})})));
  VIEWS.forEach(([id,l])=>out.push({t:'go',l,s:'',go:()=>go(id)}));
  return out;
}
function openPal(){
  if(!palItems.length) palItems=buildPal();
  $('#pal').classList.add('on'); $('#pal-q').value=''; palRender(''); $('#pal-q').focus();
}
function closePal(){$('#pal').classList.remove('on');}
function palRender(q){
  const needle=q.toLowerCase().trim();
  const hits=(needle?palItems.filter(i=>i.l.toLowerCase().includes(needle)||i.s.toLowerCase().includes(needle))
                    :palItems).slice(0,60);
  palAt=0; window._palHits=hits;
  $('#pal-list').innerHTML=hits.map((i,n)=>
    `<button role="option" data-n="${n}" aria-selected="${n===0}">
      <span class="t">${i.t}</span> ${esc(i.l)} <span class="faint">${esc(i.s)}</span></button>`).join('')
    ||'<div class="empty">Nothing matches.</div>';
  $$('#pal-list button').forEach(b=>b.onclick=()=>{closePal();hits[+b.dataset.n].go();});
}
function palKey(e){
  const hits=window._palHits||[];
  if(e.key==='Escape'){closePal();return;}
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){
    e.preventDefault(); palAt=Math.max(0,Math.min(hits.length-1,palAt+(e.key==='ArrowDown'?1:-1)));
    $$('#pal-list button').forEach((b,n)=>b.setAttribute('aria-selected',n===palAt));
    const el=$$('#pal-list button')[palAt]; if(el) el.scrollIntoView({block:'nearest'});
  }
  if(e.key==='Enter'&&hits[palAt]){closePal();hits[palAt].go();}
}
$('#pal-q').oninput=e=>palRender(e.target.value);
$('#pal').onclick=e=>{if(e.target.id==='pal')closePal();};

/* ---------- render + wiring ---------- */
function render(){
  const m=$('#main');
  if(route.course){
    if(route.tab==='papers'&&route.paper!=null){ m.innerHTML=sitPaper(route.course,route.paper); }
    else { m.innerHTML=viewCourse(route.course); $('#ctab').innerHTML=courseTab(route.course);
           if(route.tab==='questions') $('#qlist').innerHTML=qList(route.course,store.get('qf:'+route.course,'')); }
  }
  else if(route.view==='home') m.innerHTML=viewHome();
  else if(route.view==='courses') m.innerHTML=viewCourses();
  else if(route.view==='drill') m.innerHTML=viewDrill();
  else if(route.view==='quiz') m.innerHTML=viewQuiz();
  else if(route.view==='plan') m.innerHTML=viewPlan();
  else if(route.view==='cards') m.innerHTML=viewCards();
  else if(route.view==='more'){ m.innerHTML=viewMore(); $('#digest').textContent=digestText(); }
  wire();
}

function wire(){
  const m=$('#main');
  bindThumbs(m);
  m.querySelectorAll('[data-open]').forEach(el=>{
    const open=ev=>{ev.stopPropagation();go('courses',{course:el.dataset.open,tab:'method'})};
    el.onclick=open;
    el.onkeydown=ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();open(ev);}};
  });
  m.querySelectorAll('[data-back]').forEach(el=>el.onclick=()=>go('courses'));
  m.querySelectorAll('[data-back-paper]').forEach(el=>el.onclick=()=>go('courses',{course:route.course,tab:'papers'}));
  m.querySelectorAll('[data-card]').forEach(el=>el.onclick=ev=>{ev.stopPropagation();go('cards');});
  m.querySelectorAll('[data-start]').forEach(el=>el.onclick=()=>{
    store.set('drillCourse',el.dataset.start); go('drill');});
  m.querySelectorAll('[data-tab]').forEach(el=>el.onclick=()=>{
    route.tab=el.dataset.tab; route.paper=null; render();});
  m.querySelectorAll('[data-done]').forEach(el=>el.onchange=()=>{
    const k='done:'+today(), s=new Set(store.get(k,[]));
    el.checked?s.add(+el.dataset.done):s.delete(+el.dataset.done); store.set(k,[...s]);});

  const dp=$('#dpick'); if(dp) dp.onchange=()=>{store.set('drillCourse',dp.value);store.set('pos:'+dp.value,0);render();};
  m.querySelectorAll('[data-grade]').forEach(el=>el.onclick=()=>{
    const code=route.course||($('#dpick')?$('#dpick').value:null); if(!code)return;
    gradeCard(code,+el.dataset.q,+el.dataset.grade);
    store.set('pos:'+code,(store.get('pos:'+code,0)+1));
    if(route.course) {render();} else {$('#dbody').innerHTML=drillTab(code); wire();}
  });
  m.querySelectorAll('[data-skip]').forEach(el=>el.onclick=()=>{
    const code=route.course||($('#dpick')?$('#dpick').value:null); if(!code)return;
    store.set('pos:'+code,store.get('pos:'+code,0)+1);
    if(route.course){render();}else{$('#dbody').innerHTML=drillTab(code);wire();}});
  m.querySelectorAll('[data-resetq]').forEach(el=>el.onclick=()=>{
    const code=route.course||($('#dpick')?$('#dpick').value:null); if(!code)return;
    if(!confirm('Reset all grading for '+cname(code)+'?'))return;
    store.set('grade:'+code,{}); store.set('pos:'+code,0); render();});

  m.querySelectorAll('[data-sit]').forEach(el=>el.onclick=()=>{
    route.paper=+el.dataset.sit; render();});
  m.querySelectorAll('[data-sit-start]').forEach(el=>el.onclick=()=>{
    store.set('sit:'+route.course+':'+el.dataset.sitStart,{start:Date.now(),reveal:false});render();});
  m.querySelectorAll('[data-sit-reveal]').forEach(el=>el.onclick=()=>{
    const k='sit:'+route.course+':'+el.dataset.sitReveal, s=store.get(k,{});
    s.reveal=true; store.set(k,s); render();});
  m.querySelectorAll('[data-sit-reset]').forEach(el=>el.onclick=()=>{
    store.set('sit:'+route.course+':'+el.dataset.sitReset,{start:null,reveal:false});render();});

  const qt=$('#qtopic'); if(qt) qt.onchange=()=>{store.set('qf:'+route.course,qt.value);
    $('#qlist').innerHTML=qList(route.course,qt.value); wire();};

  const zr=$('#zreset'); if(zr) zr.onclick=()=>{store.set('quiz:'+Object.keys(D.quiz)[0],{});render();};
  m.querySelectorAll('[data-z]').forEach(el=>el.onclick=()=>{
    const b=Object.keys(D.quiz)[0], st=store.get('quiz:'+b,{}), i=+el.dataset.z, o=+el.dataset.o;
    if(st[i]===undefined){
      const correct=D.quiz[b].items[i].options[o].correct;
      st[i]=correct; store.set('quiz:'+b,st);
      if(!correct){const log=store.get('misses',[]);
        log.push({c:'509498',t:D.quiz[b].items[i].topic,d:today(),q:i}); store.set('misses',log.slice(-800));}
      $('#zlist').innerHTML=quizItems(b); wire();}});

  m.querySelectorAll('[data-log]').forEach(el=>el.onclick=()=>{
    const d=prompt('Log hours for which day? (YYYY-MM-DD)',today()); if(!d)return;
    const cur=loggedFor(d), v=prompt(`Actual hours on ${d} (planned ${plannedFor(d)}):`,cur==null?'':cur);
    if(v===null)return; const n=parseFloat(v);
    if(isNaN(n)){alert('Not a number.');return;}
    store.set('logged:'+d,n); render();});

  m.querySelectorAll('[data-reflow]').forEach(el=>el.onclick=()=>{
    const r=reflow();
    if(!r){alert('Nothing to re-flow — you are on or ahead of plan.');return;}
    const preview=r.plan.slice(0,12).map(([d,h])=>`  ${d}  +${h} h`).join('\n');
    const msg=`Re-flow ${r.debt} h across ${r.plan.length} remaining days.\n\n`+
      `Spare capacity available: ${r.spare} h\n`+
      (r.unplaced>0?`Cannot place: ${r.unplaced} h — you are beyond what the remaining days hold.\n`:'')+
      `\nFirst changes:\n${preview}\n\nThis adds to daily targets only. It does NOT re-solve the\n`+
      `5-day contact rule — that lives in the generator. Apply?`;
    if(!confirm(msg))return;
    const ex=store.get('extra',{});
    r.plan.forEach(([d,h])=>{ex[d]=(ex[d]||0)+h});
    store.set('extra',ex); alert('Applied. Extra hours show on the day rows.'); render();});

  m.querySelectorAll('[data-digest]').forEach(el=>el.onclick=()=>{$('#digest').textContent=digestText();});

  m.querySelectorAll('[data-export]').forEach(el=>el.onclick=()=>{
    const dump={}; store.keys().forEach(k=>{dump[k]=localStorage.getItem(k)});
    const io=$('#io'); io.style.display='block';
    io.value=JSON.stringify({exported:new Date().toISOString(),data:dump},null,1);
    io.select();
    try{ const blob=new Blob([io.value],{type:'application/json'});
      const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
      a.download='cockpit-progress-'+today()+'.json'; a.click(); URL.revokeObjectURL(a.href);
    }catch(e){}
  });
  m.querySelectorAll('[data-import]').forEach(el=>el.onclick=()=>{
    const io=$('#io'); io.style.display='block';
    if(!io.value.trim()){io.placeholder='Paste an exported JSON here, then press Import again.';io.focus();return;}
    let parsed; try{parsed=JSON.parse(io.value)}catch(e){alert('Not valid JSON.');return;}
    const data=parsed.data||parsed;
    if(!confirm('Merge '+Object.keys(data).length+' saved keys into this browser? Existing values are overwritten.'))return;
    Object.entries(data).forEach(([k,v])=>{try{localStorage.setItem(k,v)}catch(e){}});
    alert('Imported.'); render();});
}

$('#stat').textContent=D.stats;
go('home');
</script></body></html>
"""
