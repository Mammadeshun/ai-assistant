"""The cockpit's markup, styles and behaviour.

Kept out of the builder so the builder stays about data. The page works with or
without the rendered page images beside it: when `pages/` is present it shows
the real exam pages, and when it is not it falls back to extracted text, so the
same HTML serves both the full bundle and the standalone file.
"""

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Graduation cockpit</title>
<style>
:root{
  --bg:#faf9f7; --panel:#fff; --fg:#1a1917; --dim:#6f6a63; --faint:#9a948c;
  --line:#e6e1db; --line2:#efebe6; --accent:#9c4221; --accent-soft:#f6ece6;
  --warn:#9b2226; --warn-soft:#fbeaea; --ok:#1f6f43; --ok-soft:#e8f4ed;
  --hl:#fdeec2; --shadow:0 1px 2px rgba(20,16,12,.05),0 4px 14px rgba(20,16,12,.05);
  --r:12px;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#121110; --panel:#1b1a18; --fg:#eeebe6; --dim:#a09a91; --faint:#7c766e;
  --line:#2c2926; --line2:#232120; --accent:#e08a5a; --accent-soft:#2b201a;
  --warn:#ef8080; --warn-soft:#2e1c1c; --ok:#74c79a; --ok-soft:#16281f;
  --hl:#4a3b18; --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.25);
}}
:root[data-theme=dark]{
  --bg:#121110; --panel:#1b1a18; --fg:#eeebe6; --dim:#a09a91; --faint:#7c766e;
  --line:#2c2926; --line2:#232120; --accent:#e08a5a; --accent-soft:#2b201a;
  --warn:#ef8080; --warn-soft:#2e1c1c; --ok:#74c79a; --ok-soft:#16281f;
  --hl:#4a3b18; --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.25);
}
:root[data-theme=light]{
  --bg:#faf9f7; --panel:#fff; --fg:#1a1917; --dim:#6f6a63; --faint:#9a948c;
  --line:#e6e1db; --line2:#efebe6; --accent:#9c4221; --accent-soft:#f6ece6;
  --warn:#9b2226; --warn-soft:#fbeaea; --ok:#1f6f43; --ok-soft:#e8f4ed;
  --hl:#fdeec2; --shadow:0 1px 2px rgba(20,16,12,.05),0 4px 14px rgba(20,16,12,.05);
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--fg);
  font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-text-size-adjust:100%;overflow-wrap:break-word}
a{color:var(--accent)}
/* ---------- shell ---------- */
.top{position:sticky;top:0;z-index:40;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:saturate(1.6) blur(12px);border-bottom:1px solid var(--line)}
.top-in{max-width:1080px;margin:0 auto;padding:10px 16px;display:flex;gap:10px;align-items:center}
.brand{font-weight:680;letter-spacing:-.01em;font-size:1rem;white-space:nowrap}
.brand span{color:var(--dim);font-weight:400;font-size:.8rem;margin-left:8px}
.grow{flex:1}
.iconbtn{border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:9px;
  width:36px;height:36px;display:grid;place-items:center;cursor:pointer;font-size:.95rem;flex:none}
.shell{max-width:1080px;margin:0 auto;padding:0 16px 96px;display:flex;gap:22px}
.rail{display:none;flex:0 0 176px;position:sticky;top:64px;align-self:flex-start;padding-top:18px}
.rail button{display:flex;gap:9px;align-items:center;width:100%;text-align:left;border:0;background:none;
  color:var(--dim);font:inherit;font-size:.9rem;padding:8px 10px;border-radius:9px;cursor:pointer}
.rail button:hover{background:var(--line2);color:var(--fg)}
.rail button[aria-selected=true]{background:var(--accent-soft);color:var(--accent);font-weight:620}
.main{flex:1;min-width:0;padding-top:18px}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:40;display:flex;
  background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(12px);
  border-top:1px solid var(--line);padding:6px 4px calc(6px + env(safe-area-inset-bottom))}
.tabbar button{flex:1;border:0;background:none;color:var(--faint);font:inherit;font-size:.66rem;
  display:flex;flex-direction:column;align-items:center;gap:3px;padding:5px 2px;cursor:pointer}
.tabbar button b{font-size:1.05rem;font-weight:400;line-height:1}
.tabbar button[aria-selected=true]{color:var(--accent)}
@media(min-width:860px){.rail{display:block}.tabbar{display:none}.shell{padding-bottom:48px}}
/* ---------- primitives ---------- */
h1{font-size:1.5rem;margin:.1em 0 .5em;letter-spacing:-.02em}
h2{font-size:1.06rem;margin:1.7em 0 .6em;letter-spacing:-.01em}
h3{font-size:.95rem;margin:1.2em 0 .4em}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
  padding:14px 16px;margin:10px 0;box-shadow:var(--shadow)}
.card.tight{padding:11px 13px}
.row{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
.dim{color:var(--dim)}.faint{color:var(--faint)}
.small{font-size:.84rem}.xs{font-size:.76rem}
.big{font-size:2.4rem;font-weight:700;line-height:1;letter-spacing:-.03em}
.kicker{font-size:.68rem;text-transform:uppercase;letter-spacing:.09em;color:var(--faint);font-weight:640}
.pill{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:99px;
  border:1px solid var(--line);font-size:.73rem;color:var(--dim);margin:0 5px 5px 0;white-space:nowrap}
.pill.a{border-color:color-mix(in srgb,var(--accent) 40%,transparent);color:var(--accent);background:var(--accent-soft)}
.pill.g{border-color:color-mix(in srgb,var(--ok) 40%,transparent);color:var(--ok);background:var(--ok-soft)}
.pill.r{border-color:color-mix(in srgb,var(--warn) 40%,transparent);color:var(--warn);background:var(--warn-soft)}
.gate{background:var(--warn-soft);border-left:3px solid var(--warn);color:var(--fg);
  padding:10px 13px;border-radius:0 9px 9px 0;font-size:.88rem;margin:10px 0}
.note{background:var(--accent-soft);border-left:3px solid var(--accent);
  padding:10px 13px;border-radius:0 9px 9px 0;font-size:.88rem;margin:10px 0}
.bar{height:6px;background:var(--line);border-radius:99px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--accent);border-radius:99px;transition:width .25s}
.grid{display:grid;gap:10px}
@media(min-width:620px){.grid.two{grid-template-columns:1fr 1fr}}
button.act,select,input[type=search],input[type=text]{font:inherit;font-size:.9rem;
  padding:9px 12px;border-radius:9px;border:1px solid var(--line);background:var(--panel);color:var(--fg)}
button.act{cursor:pointer}
button.act:hover{border-color:var(--accent);color:var(--accent)}
button.act.on{background:var(--accent);border-color:var(--accent);color:#fff}
input[type=search]{width:100%}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:.87rem}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line2);vertical-align:top}
th{color:var(--faint);font-weight:640;font-size:.7rem;text-transform:uppercase;letter-spacing:.07em}
tr.past td{opacity:.42}
blockquote{margin:9px 0;padding:11px 14px;background:var(--bg);border:1px solid var(--line2);
  border-radius:9px;font-size:.89rem;white-space:pre-wrap}
mark{background:var(--hl);color:inherit;padding:0 2px;border-radius:3px}
.click{cursor:pointer}
.click:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
label.chk{display:flex;gap:10px;align-items:flex-start;cursor:pointer;padding:3px 0}
input[type=checkbox]{margin-top:5px;flex:none;width:17px;height:17px;accent-color:var(--accent)}
.empty{text-align:center;color:var(--faint);padding:34px 16px;font-size:.9rem}
.back{border:0;background:none;color:var(--accent);font:inherit;font-size:.86rem;
  cursor:pointer;padding:6px 0;display:inflex;gap:6px}
/* ---------- paper viewer ---------- */
.thumbs{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px;margin-top:10px}
.thumb{border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff;cursor:zoom-in;
  aspect-ratio:1/1.41;position:relative}
.thumb img{width:100%;height:100%;object-fit:cover;object-position:top;display:block}
.thumb b{position:absolute;left:5px;bottom:5px;background:rgba(0,0,0,.62);color:#fff;
  font-size:.64rem;font-weight:500;padding:1px 6px;border-radius:99px}
.lb{position:fixed;inset:0;z-index:90;background:rgba(12,10,9,.95);display:none;
  flex-direction:column;overscroll-behavior:contain}
.lb.on{display:flex}
.lb-bar{display:flex;align-items:center;gap:10px;padding:10px 14px;color:#eee;font-size:.84rem;flex:none}
.lb-bar button{border:1px solid #4a4640;background:#222;color:#eee;border-radius:8px;
  padding:7px 12px;font:inherit;font-size:.84rem;cursor:pointer}
.lb-body{flex:1;overflow:auto;display:flex;align-items:flex-start;justify-content:center;padding:0 8px 20px}
.lb-body img{max-width:100%;height:auto;border-radius:6px;background:#fff}
.lb-body.zoom{align-items:flex-start;justify-content:flex-start}
.lb-body.zoom img{max-width:none;width:190%}
/* ---------- drill / quiz ---------- */
.opt{display:block;width:100%;text-align:left;padding:10px 13px;margin:6px 0;border:1px solid var(--line);
  border-radius:9px;font:inherit;font-size:.88rem;background:var(--panel);color:var(--fg);cursor:pointer}
.opt:hover{border-color:var(--accent)}
.opt.right{border-color:var(--ok);background:var(--ok-soft);color:var(--ok)}
.opt.wrong{border-color:var(--warn);background:var(--warn-soft);color:var(--warn)}
.opt:disabled{cursor:default}
.rate{display:flex;gap:7px;margin-top:10px;flex-wrap:wrap}
.rate button{flex:1;min-width:82px}
details>summary{cursor:pointer;font-weight:620;font-size:.9rem;list-style:none;padding:3px 0}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"▸ ";color:var(--faint)}
details[open]>summary::before{content:"▾ "}
.md h1,.md h2,.md h3{font-size:.95rem;margin:1.1em 0 .35em}
.md ul,.md ol{padding-left:20px;margin:.45em 0}
.md li{margin:.3em 0;font-size:.9rem}
.md p{font-size:.9rem;margin:.5em 0}
.md code{background:var(--line2);padding:1px 5px;border-radius:5px;font-size:.85em}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
</style></head><body>

<header class="top"><div class="top-in">
  <div class="brand">Cockpit <span id="stat"></span></div>
  <div class="grow"></div>
  <button class="iconbtn" id="go-search" title="Search (press /)">⌕</button>
  <button class="iconbtn" id="go-theme" title="Theme">◐</button>
</div></header>

<div class="shell">
  <nav class="rail" id="rail"></nav>
  <main class="main" id="main"></main>
</div>

<nav class="tabbar" id="tabbar"></nav>

<div class="lb" id="lb">
  <div class="lb-bar">
    <button id="lb-close">✕ Close</button>
    <button id="lb-prev">‹ Prev</button>
    <span id="lb-label" class="grow" style="text-align:center"></span>
    <button id="lb-next">Next ›</button>
    <button id="lb-zoom">Zoom</button>
  </div>
  <div class="lb-body" id="lb-body"><img id="lb-img" alt=""></div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
"use strict";
const D=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const store={
  get(k,d){try{const v=localStorage.getItem('ck:'+k);return v==null?d:JSON.parse(v)}catch(e){return d}},
  set(k,v){try{localStorage.setItem('ck:'+k,JSON.stringify(v))}catch(e){}}
};
const today=()=>new Date().toISOString().slice(0,10);
const dayDiff=(a,b)=>Math.round((new Date(a)-new Date(b))/864e5);
const cname=c=>(D.names[c]||(D.lib[c]&&D.lib[c].name)||c);
const plural=(n,w)=>n+' '+w+(n===1?'':'s');

/* ---------------- theme ---------------- */
const themeBtn=$('#go-theme');
function applyTheme(t){ if(t) document.documentElement.setAttribute('data-theme',t);
  else document.documentElement.removeAttribute('data-theme'); }
applyTheme(store.get('theme',null));
themeBtn.onclick=()=>{const cur=store.get('theme',null);
  const nxt=cur==='dark'?'light':cur==='light'?null:'dark';
  store.set('theme',nxt);applyTheme(nxt);};

/* ---------------- routing ---------------- */
const VIEWS=[
  ['home','Today','◈'],['courses','Courses','▤'],['drill','Drill','◇'],
  ['quiz','Quiz','✓'],['plan','Plan','▦'],['search','Search','⌕'],
];
let route={view:'home',course:null,tab:'method'};

$('#rail').innerHTML=VIEWS.map(([id,label,icon])=>
  `<button data-v="${id}"><span>${icon}</span> ${label}</button>`).join('');
$('#tabbar').innerHTML=VIEWS.map(([id,label,icon])=>
  `<button data-v="${id}"><b>${icon}</b>${label}</button>`).join('');
$$('#rail button,#tabbar button').forEach(b=>b.onclick=()=>go(b.dataset.v));
$('#go-search').onclick=()=>go('search');

function go(view,opts={}){ route={view,course:opts.course??null,tab:opts.tab??'method'};
  $$('#rail button,#tabbar button').forEach(b=>b.setAttribute('aria-selected',b.dataset.v===view));
  render(); window.scrollTo(0,0);
  if(view==='search') setTimeout(()=>$('#sq')&&$('#sq').focus(),40);
}
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&$('#lb').classList.contains('on')){closeLb();return;}
  if(e.target.matches('input,textarea,select'))return;
  if(e.key==='/'){e.preventDefault();go('search');}
});

/* ---------------- helpers ---------------- */
function progressOf(code){
  const bank=D.drill[code]; if(!bank||!bank.cards.length) return null;
  const done=store.get('drilled:'+code,[]).length;
  return {done,total:bank.cards.length,pct:Math.round(100*done/bank.cards.length)};
}
function examOf(code){ return D.exams.find(e=>e.code===code)||D.winter.find(w=>w.code===code)||null; }
function countdown(code){ const e=D.exams.find(x=>x.code===code); if(!e) return null;
  const d=dayDiff(e.date,today()); return d<0?null:d; }

function md(src){
  const out=[];let table=false;
  for(let ln of src.split('\n')){
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
    .replace(/(<li>[\s\S]*?<\/li>\n?)+/g,m=>m.includes('<ol>')?m:'<ul>'+m+'</ul>');
}
function fmt(s){ return esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<code>$1</code>'); }

/* ---------------- lightbox ---------------- */
let lbSet=[],lbAt=0;
function openLb(files,at,label){ lbSet=files;lbAt=at;
  $('#lb-label').textContent=label; $('#lb').classList.add('on');
  $('#lb-body').classList.remove('zoom'); showLb(); }
function showLb(){ $('#lb-img').src=D.pagesDir+lbSet[lbAt];
  $('#lb-label').dataset.n=(lbAt+1)+' / '+lbSet.length;
  $('#lb-label').textContent=$('#lb-label').dataset.base+' — page '+(lbAt+1)+' of '+lbSet.length;
  $('#lb-body').scrollTop=0; }
function closeLb(){ $('#lb').classList.remove('on'); $('#lb-img').src=''; }
$('#lb-close').onclick=closeLb;
$('#lb-prev').onclick=()=>{if(lbAt>0){lbAt--;showLb();}};
$('#lb-next').onclick=()=>{if(lbAt<lbSet.length-1){lbAt++;showLb();}};
$('#lb-zoom').onclick=()=>$('#lb-body').classList.toggle('zoom');
document.addEventListener('keydown',e=>{ if(!$('#lb').classList.contains('on'))return;
  if(e.key==='ArrowRight')$('#lb-next').click(); if(e.key==='ArrowLeft')$('#lb-prev').click(); });

function paperBlock(code,doc){
  const files=D.pages[code+':'+doc.i];
  if(!files||!files.length) return '';
  return `<div class="thumbs">`+files.map((f,i)=>
    `<div class="thumb click" data-pg="${code}:${doc.i}" data-at="${i}" data-name="${esc(doc.name)}">
       <img loading="lazy" src="${D.pagesDir}${f}" alt="page ${i+1}"><b>${i+1}</b></div>`).join('')+`</div>`;
}
function bindThumbs(root){
  root.querySelectorAll('.thumb').forEach(t=>t.onclick=()=>{
    const files=D.pages[t.dataset.pg];
    $('#lb-label').dataset.base=t.dataset.name;
    openLb(files,+t.dataset.at,t.dataset.name);
  });
}

/* ---------------- views ---------------- */
function viewHome(){
  const t=today();
  const upcoming=D.exams.filter(e=>e.date>=t).sort((a,b)=>a.date<b.date?-1:1);
  const n=upcoming[0];
  let h='<h1>Today</h1>';
  if(n){const d=dayDiff(n.date,t);
    h+=`<div class="card"><div class="kicker">next exam</div>
      <div class="row" style="margin-top:6px">
        <div><div class="big">${d===0?'today':plural(d,'day')}</div>
          <div style="margin-top:4px;font-weight:620">${esc(n.name)}</div></div>
        <div class="small dim" style="text-align:right">${n.date}<br>${esc(n.campus)}</div></div>
      <div class="gate">${esc(n.gate)}</div>
      <button class="act" data-open="${n.code}">Open course →</button></div>`;
  } else h+='<div class="card empty">No exams ahead. Either the plan has not started or it is over.</div>';

  const soon=D.exams.filter(e=>e.book_by>=t&&dayDiff(e.book_by,t)<=5);
  if(soon.length) h+=`<div class="card"><div class="kicker">booking closes soon</div>`+
    soon.map(e=>`<div class="row" style="margin-top:7px"><span>${esc(e.name)}</span>
      <span class="pill r">by ${e.book_by.slice(5)}</span></div>`).join('')+`</div>`;

  const slots=D.calendar[t]||[];
  h+='<h2>Today&rsquo;s plan</h2>';
  if(!slots.length) h+='<div class="card empty">Nothing scheduled for today.</div>';
  else{ const done=store.get('done:'+t,[]);
    h+='<div class="card">'+slots.map((s,i)=>
      `<label class="chk"><input type="checkbox" data-done="${i}" ${done.includes(i)?'checked':''}>
       <span><b>${esc(cname(s[0]))}</b> <span class="dim small">${s[1]} h</span></span></label>`).join('')+
      '</div>';}

  h+='<h2>Next two weeks</h2><div class="card scroll"><table><tr><th>Date</th><th>h</th><th>Work</th></tr>'+
    Object.keys(D.calendar).filter(d=>d>=t).slice(0,14).map(d=>{
      const ex=D.exams.find(e=>e.date===d);
      const w=(D.calendar[d]||[]).map(s=>esc(cname(s[0]))+' <span class="faint">'+s[1]+'h</span>').join(', ')||'—';
      const hrs=(D.calendar[d]||[]).reduce((a,s)=>a+s[1],0);
      return `<tr><td>${d.slice(5)}</td><td>${hrs||''}</td><td>${ex?'<b style="color:var(--accent)">EXAM · '+esc(ex.name)+'</b><br>':''}${w}</td></tr>`;
    }).join('')+'</table></div>';
  return h;
}

function viewCourses(){
  const t=today();
  const sep=D.exams.slice().sort((a,b)=>a.date<b.date?-1:1);
  const card=(e,winter)=>{
    const lib=D.lib[e.code]||{documents:[],questions:[]};
    const papers=lib.documents.filter(d=>d.role==='paper').length;
    const keys=lib.documents.filter(d=>d.role==='solution').length;
    const p=progressOf(e.code); const cd=countdown(e.code);
    return `<div class="card click" data-open="${e.code}">
      <div class="row"><b>${esc(e.name)}</b>
        <span class="small dim">${winter?'Jan/Feb':e.date.slice(5)+' · '+esc(e.campus)}</span></div>
      <div style="margin-top:7px">
        ${cd!=null?`<span class="pill ${cd<=7?'r':'a'}">${cd===0?'today':plural(cd,'day')}</span>`:''}
        <span class="pill">${e.cfu} CFU</span><span class="pill">${e.hours} h</span>
        ${papers?`<span class="pill">${plural(papers,'paper')}</span>`:'<span class="pill r">no papers</span>'}
        ${keys?`<span class="pill g">${plural(keys,'key')}</span>`:''}
        ${lib.questions.length?`<span class="pill">${lib.questions.length} questions</span>`:''}
      </div>
      ${p?`<div class="bar" style="margin-top:9px"><i style="width:${p.pct}%"></i></div>
          <div class="xs faint" style="margin-top:5px">${p.done} of ${p.total} drilled</div>`:''}
    </div>`;
  };
  return '<h1>Courses</h1><div class="kicker">September</div>'+sep.map(e=>card(e,false)).join('')+
    '<div class="kicker" style="margin-top:22px">January / February</div>'+
    D.winter.map(w=>card(w,true)).join('')+
    '<div class="card small dim">Winter dates are not published — Esse3 returns nothing for 2027.</div>';
}

function viewCourse(code){
  const e=examOf(code)||{name:cname(code),cfu:'',hours:'',gate:''};
  const lib=D.lib[code]||{documents:[],questions:[]};
  const tabs=[['method','Method'],['papers','Papers'],['questions','Questions'],['files','Files']];
  const cd=countdown(code);
  let h=`<button class="back" data-back="1">← All courses</button>
    <h1 style="margin-top:6px">${esc(e.name)}</h1>
    <div style="margin-bottom:6px">
      ${cd!=null?`<span class="pill ${cd<=7?'r':'a'}">${cd===0?'today':plural(cd,'day')}</span>`:''}
      ${e.date?`<span class="pill">${e.date} · ${esc(e.campus||'')}</span>`:'<span class="pill">Jan/Feb</span>'}
      ${e.cfu?`<span class="pill">${e.cfu} CFU</span>`:''}${e.hours?`<span class="pill">${e.hours} h</span>`:''}
      ${e.book_by?`<span class="pill r">book by ${e.book_by.slice(5)}</span>`:''}
    </div>`;
  if(e.gate) h+=`<div class="gate"><b>Pass gate.</b> ${esc(e.gate)}</div>`;
  if(e.note) h+=`<div class="note">${esc(e.note)}</div>`;
  h+='<div style="display:flex;gap:7px;flex-wrap:wrap;margin:14px 0 4px">'+
    tabs.map(([id,label])=>`<button class="act ${route.tab===id?'on':''}" data-tab="${id}">${label}</button>`).join('')+
    '</div><div id="ctab"></div>';
  return h;
}

function courseTab(code){
  const lib=D.lib[code]||{documents:[],questions:[]};
  if(route.tab==='method'){
    const pack=D.packs[code];
    return pack?`<div class="card md">${md(pack)}</div>`
               :'<div class="card empty">No study pack for this course.</div>';
  }
  if(route.tab==='papers'){
    const papers=lib.documents.filter(d=>(d.role==='paper'||d.role==='solution')&&(D.pages[code+':'+d.i]||d.chars));
    if(!papers.length) return '<div class="card empty">No exam papers are archived for this course.</div>';
    const shown=papers.filter(d=>D.pages[code+':'+d.i]).length;
    return `<div class="small dim" style="margin:10px 0">${plural(papers.length,'document')}${
        shown?` · ${shown} viewable as pages`:' · no page images in this build'}</div>`+
      papers.map(d=>{
      const imgs=paperBlock(code,d);
      // With no page image the extracted text is all there is, so do not hide
      // it behind a disclosure the way we do when the real page is on screen.
      const open=imgs?'':' open';
      return `<div class="card"><div class="row"><b>${esc(d.name)}</b>
        <span class="pill ${d.role==='solution'?'g':'a'}">${d.role}</span></div>
        ${imgs||''}
        ${d.chars?`<details${open} style="margin-top:10px"><summary>${imgs?'Extracted text':'Text (no page image for this file)'}${
            d.text.startsWith('[OCR')?' · OCR, expect errors':''}</summary>
          <blockquote>${esc(d.text.slice(0,14000))}</blockquote></details>`
         :'<div class="small faint" style="margin-top:8px">No text layer — read the pages above.</div>'}
      </div>`;}).join('');
  }
  if(route.tab==='questions'){
    const qs=lib.questions;
    if(!qs.length) return '<div class="card empty">No questions were extracted for this course.</div>';
    const topics=[...new Set(qs.map(q=>q.topic))].sort();
    const f=store.get('qf:'+code,'');
    return `<div class="card tight"><select id="qtopic">
        <option value="">All topics (${qs.length})</option>
        ${topics.map(t=>`<option ${f===t?'selected':''}>${esc(t)}</option>`).join('')}
      </select></div><div id="qlist">${qList(code,f)}</div>`;
  }
  const docs=lib.documents.slice().sort((a,b)=>{
    const o={paper:0,solution:1,material:2,'image-only':3,stub:4};
    return (o[a.role]-o[b.role])||b.chars-a.chars;});
  return docs.map(d=>`<details class="card"><summary>${esc(d.name)}</summary>
    <div style="margin:8px 0"><span class="pill ${d.role==='paper'?'a':d.role==='solution'?'g':d.role==='stub'?'r':''}">${d.role}</span>
      <span class="pill">${d.kind}</span><span class="pill">${d.chars.toLocaleString()} chars</span></div>
    ${paperBlock(code,d)}
    ${d.chars?`<blockquote>${esc(d.text.slice(0,14000))}</blockquote>`
      :`<div class="small faint">No text layer. Original file:<br><code>${esc(d.path)}</code></div>`}
  </details>`).join('');
}
function qList(code,filter){
  const qs=(D.lib[code].questions||[]).filter(q=>!filter||q.topic===filter);
  return `<div class="small dim" style="margin:10px 0">${plural(qs.length,'question')}</div>`+
    qs.map(q=>`<div class="card"><div>
      <span class="pill a">${esc(q.topic)}</span>
      ${q.marks?`<span class="pill">${q.marks} marks</span>`:''}
      ${q.mcq?'<span class="pill g">multiple choice</span>':''}
      ${q.answer?'<span class="pill g">answer published</span>':''}</div>
      <blockquote>${esc(q.text)}</blockquote>
      ${q.answer?`<details><summary>Show worked answer</summary>
        <blockquote style="border-left:3px solid var(--ok)">${esc(q.answer)}</blockquote></details>`:''}
      <div class="xs faint">${esc(q.paper)}</div></div>`).join('');
}

function viewDrill(){
  const codes=Object.keys(D.drill).sort((a,b)=>{
    const ca=countdown(a),cb=countdown(b);
    return (ca==null?999:ca)-(cb==null?999:cb);});
  if(!codes.length) return '<div class="card empty">No recurring question types were found.</div>';
  const cur=store.get('drillCourse',codes[0]);
  const code=codes.includes(cur)?cur:codes[0];
  const bank=D.drill[code], p=progressOf(code);
  return `<h1>Drill</h1>
    <div class="card tight"><select id="dpick">${codes.map(c=>
      `<option value="${c}" ${c===code?'selected':''}>${esc(cname(c))} (${D.drill[c].cards.length})</option>`).join('')}</select></div>
    <div class="card tight"><div class="bar"><i style="width:${p.pct}%"></i></div>
      <div class="row" style="margin-top:7px"><span class="small dim">${p.done} of ${p.total} worked</span>
      <button class="act" id="dreset">reset</button></div></div>
    <div id="dcards">${drillCards(code)}</div>`;
}
function drillCards(code){
  const bank=D.drill[code], done=new Set(store.get('drilled:'+code,[]));
  return bank.cards.map((q,i)=>`<div class="card" style="${done.has(i)?'opacity:.5':''}">
    <div><span class="pill a">${esc(q.topic)}</span>
      <span class="pill">${plural(q.seen,'paper')} · ${Math.round(q.share*100)}%</span>
      ${q.marks?`<span class="pill">${q.marks} marks</span>`:''}</div>
    <blockquote>${esc(q.text)}</blockquote>
    ${q.answer?`<details><summary>Show worked answer</summary>
      <blockquote style="border-left:3px solid var(--ok)">${esc(q.answer)}</blockquote></details>`:''}
    <div class="xs faint">${q.key?'Solution published in: <b>'+esc(q.key)+'</b>':'No published solution.'}</div>
    <div class="xs faint">In: ${q.papers.map(esc).join(' · ')}</div>
    <div class="rate"><button class="act" data-d="${i}" data-v="1">${done.has(i)?'✓ worked':'Mark worked'}</button></div>
  </div>`).join('');
}

function viewQuiz(){
  const banks=Object.keys(D.quiz);
  if(!banks.length) return '<div class="card empty">No answer-keyed quiz is available.</div>';
  const b=banks[0], bank=D.quiz[b], state=store.get('quiz:'+b,{});
  const answered=Object.keys(state).length, right=Object.values(state).filter(Boolean).length;
  return `<h1>Quiz</h1>
    <div class="card tight"><div class="row"><b>${esc(bank.name)}</b>
      <span class="small dim">${bank.items.length} questions</span></div>
      <div class="xs faint" style="margin-top:4px">${esc(bank.source)}</div>
      <div class="bar" style="margin-top:9px"><i style="width:${Math.round(100*answered/bank.items.length)}%"></i></div>
      <div class="row" style="margin-top:7px"><span class="small dim">${answered} answered · ${right} correct
        ${answered?`(${Math.round(100*right/answered)}%)`:''}</span>
      <button class="act" id="zreset">reset</button></div></div>
    <div id="zlist">${quizItems(b)}</div>`;
}
function quizItems(b){
  const bank=D.quiz[b], state=store.get('quiz:'+b,{});
  return bank.items.map((q,i)=>{
    const shown=state[i]!==undefined;
    return `<div class="card"><div><span class="pill a">${esc(q.topic)}</span>
      ${q.n?`<span class="pill">#${q.n}</span>`:''}
      ${shown?(state[i]?'<span class="pill g">correct</span>':'<span class="pill r">wrong</span>'):''}</div>
      <div style="margin:8px 0 4px;font-size:.93rem">${esc(q.stem)}</div>
      ${q.options.map((o,j)=>`<button class="opt ${shown?(o.correct?'right':'wrong'):''}"
        data-z="${i}" data-o="${j}" ${shown?'disabled':''}>${esc(o.letter)}. ${esc(o.text)}${shown&&o.correct?' ✓':''}</button>`).join('')}
    </div>`;}).join('');
}

function viewPlan(){
  const t=today();
  let h='<h1>Plan</h1><h2>September</h2><div class="card scroll"><table>'+
    '<tr><th>Date</th><th>Course</th><th>Where</th><th>Book by</th><th>h</th><th>CFU</th></tr>'+
    D.exams.map(e=>`<tr class="${e.date<t?'past':''}"><td>${e.date.slice(5)}</td>
      <td>${esc(e.name)}</td><td>${esc(e.campus)}</td><td>${e.book_by.slice(5)}</td>
      <td>${e.hours}</td><td>${e.cfu}</td></tr>`).join('')+'</table></div>';
  h+='<h2>January / February</h2><div class="card scroll"><table><tr><th>Course</th><th>h</th><th>CFU</th></tr>'+
    D.winter.map(w=>`<tr><td>${esc(w.name)}</td><td>${w.hours}</td><td>${w.cfu}</td></tr>`).join('')+'</table></div>';
  h+='<h2>Full calendar</h2><div class="card scroll"><table><tr><th>Date</th><th>h</th><th>Work</th></tr>'+
    Object.keys(D.calendar).map(d=>{
      const ex=D.exams.find(e=>e.date===d);
      const w=(D.calendar[d]||[]).map(s=>esc(cname(s[0]))+' <span class="faint">'+s[1]+'h</span>').join(', ')||'—';
      const hrs=(D.calendar[d]||[]).reduce((a,s)=>a+s[1],0);
      return `<tr class="${d<t?'past':''}"><td>${d.slice(5)}</td><td>${hrs||''}</td>
        <td>${ex?'<b style="color:var(--accent)">EXAM · '+esc(ex.name)+'</b><br>':''}${w}</td></tr>`;
    }).join('')+'</table></div>';
  return h;
}

function viewSearch(){
  return `<h1>Search</h1>
    <div class="card tight"><input type="search" id="sq" placeholder="Search every paper, question and document…"
      value="${esc(store.get('sq',''))}"></div>
    <div id="sres"></div>`;
}
function runSearch(){
  const q=$('#sq').value.trim(); store.set('sq',q);
  if(q.length<3){$('#sres').innerHTML='<div class="empty">Type at least three characters.</div>';return;}
  const rx=new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'ig');
  const byCourse={}; let total=0;
  outer:
  for(const c of Object.keys(D.lib)){
    for(const qn of D.lib[c].questions){
      rx.lastIndex=0;
      if(rx.test(qn.text)){ (byCourse[c]=byCourse[c]||[]).push({kind:'question',src:qn.paper,txt:qn.text});
        if(++total>200)break outer; }
    }
    for(const d of D.lib[c].documents){
      if(!d.chars)continue; rx.lastIndex=0; let m,n=0;
      while((m=rx.exec(d.text))&&n<2){
        const s=Math.max(0,m.index-100),e=Math.min(d.text.length,m.index+180);
        (byCourse[c]=byCourse[c]||[]).push({kind:'document',src:d.name,txt:d.text.slice(s,e)});
        n++; if(++total>200)break outer;
      }
    }
  }
  const keys=Object.keys(byCourse);
  $('#sres').innerHTML=`<div class="small dim" style="margin:12px 0">${total}${total>200?'+':''} matches in ${plural(keys.length,'course')}</div>`+
    keys.map(c=>`<div class="kicker" style="margin-top:16px">${esc(cname(c))}</div>`+
      byCourse[c].slice(0,12).map(r=>`<div class="card tight">
        <div class="xs faint">${r.kind} · ${esc(r.src)}</div>
        <blockquote style="margin-top:6px">${esc(r.txt).replace(rx,m=>'<mark>'+m+'</mark>')}</blockquote></div>`).join('')
    ).join('')||'<div class="empty">Nothing found.</div>';
}

/* ---------------- render ---------------- */
function render(){
  const main=$('#main');
  if(route.course){ main.innerHTML=viewCourse(route.course);
    $('#ctab').innerHTML=courseTab(route.course); }
  else if(route.view==='home') main.innerHTML=viewHome();
  else if(route.view==='courses') main.innerHTML=viewCourses();
  else if(route.view==='drill') main.innerHTML=viewDrill();
  else if(route.view==='quiz') main.innerHTML=viewQuiz();
  else if(route.view==='plan') main.innerHTML=viewPlan();
  else if(route.view==='search'){ main.innerHTML=viewSearch(); wireSearch(); }
  wire();
}
function wire(){
  const main=$('#main');
  bindThumbs(main);
  main.querySelectorAll('[data-open]').forEach(el=>el.onclick=ev=>{
    ev.stopPropagation(); go('courses',{course:el.dataset.open,tab:'method'});});
  main.querySelectorAll('[data-back]').forEach(el=>el.onclick=()=>go('courses'));
  main.querySelectorAll('[data-tab]').forEach(el=>el.onclick=()=>{
    route.tab=el.dataset.tab;
    main.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('on',b===el));
    $('#ctab').innerHTML=courseTab(route.course); wireInner();});
  main.querySelectorAll('[data-done]').forEach(el=>el.onchange=()=>{
    const k='done:'+today(); const s=new Set(store.get(k,[]));
    el.checked?s.add(+el.dataset.done):s.delete(+el.dataset.done); store.set(k,[...s]);});
  const dp=$('#dpick'); if(dp) dp.onchange=()=>{store.set('drillCourse',dp.value);render();};
  const dr=$('#dreset'); if(dr) dr.onclick=()=>{store.set('drilled:'+$('#dpick').value,[]);render();};
  main.querySelectorAll('[data-d]').forEach(el=>el.onclick=()=>{
    const code=$('#dpick').value, k='drilled:'+code, s=new Set(store.get(k,[])), i=+el.dataset.d;
    s.has(i)?s.delete(i):s.add(i); store.set(k,[...s]); render();});
  const zr=$('#zreset'); if(zr) zr.onclick=()=>{store.set('quiz:'+Object.keys(D.quiz)[0],{});render();};
  main.querySelectorAll('[data-z]').forEach(el=>el.onclick=()=>{
    const b=Object.keys(D.quiz)[0], st=store.get('quiz:'+b,{}), i=+el.dataset.z, o=+el.dataset.o;
    if(st[i]===undefined){ st[i]=D.quiz[b].items[i].options[o].correct; store.set('quiz:'+b,st);
      $('#zlist').innerHTML=quizItems(b); wire(); }});
  wireInner();
}
function wireInner(){
  const qt=$('#qtopic');
  if(qt) qt.onchange=()=>{ store.set('qf:'+route.course,qt.value);
    $('#qlist').innerHTML=qList(route.course,qt.value); };
  bindThumbs($('#main'));
}
function wireSearch(){
  let t; const el=$('#sq');
  el.oninput=()=>{clearTimeout(t);t=setTimeout(runSearch,200)};
  if(el.value.trim().length>=3) runSearch();
}

$('#stat').textContent=D.stats;
go('home');
</script></body></html>
"""
