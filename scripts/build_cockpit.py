#!/usr/bin/env python3
"""Build the offline study cockpit: one self-contained HTML file.

Everything is inlined - no network, no CDN, no fonts - because the times you
most need it are on a train to Milan and in a corridor ten minutes before a
sitting. Progress is kept in localStorage on the device; nothing is uploaded.

Seven views:
  Today      what the calendar says to work on, with a countdown
  Exams      every sitting with its pass gate, campus, and booking deadline
  Method     the study pack per course: order, skips, tactic for 18
  Drill      recurring question types, most-frequent first
  Questions  every extracted question, filterable by course and topic
  Library    every archived document, readable in full
  Quiz       the answer-keyed multiple-choice banks
  Search     across every document and question
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path("data/cockpit.html")

EXAMS = [
    ("509496", "Information Retrieval & RecSys", "2026-08-31", "Pavia", 30, 6,
     "Project + presentation. No written paper. Autumn presentation slot UNCONFIRMED.", "2026-08-26"),
    ("509521", "Laboratory of Machine Learning", "2026-09-01", "Pavia", 25, 3,
     "Nine report submissions — the reports are the grade. Check the windows are open.", "2026-08-27"),
    ("509519", "Ethics, Law and AI", "2026-09-02", "Pavia", 28, 12,
     "Multiple choice, single unsplit exam. No gate beyond 18.", "2026-08-28"),
    ("509494", "Brain Modelling", "2026-09-03", "Pavia", 26, 6,
     "Coding project 30% + written 70%. The project mark carries to later sessions.", "2026-08-29"),
    ("509495", "Data Mining", "2026-09-04", "Pavia", 19, 6,
     "Assignments (12/30) were set during delivery and cannot be recovered — you sit for the full 30.", "2026-08-30"),
    ("509485", "Cognitive Psychology", "2026-09-08", "Bicocca", 27, 6,
     "Written 25 pts + COMPULSORY ORAL 6 pts. Edition 7392 binds: threshold 12, marks summed. Do not contact Bricolo.", "2026-09-03"),
    ("509477", "Computer Programming", "2026-09-09", "Statale", 44, 12,
     "TWO GATES: theory >=12/20 AND code >=6/10. Non-running code is an automatic fail.", "2026-09-04"),
    ("509481", "Calculus", "2026-09-11", "Pavia", 44, 12,
     "Part 1 >=15/30 on top of the overall 18. Closed book. No Part1/Part2 split exists in autumn 2026.", "2026-09-06"),
    ("509486", "Machine Learning / ANN / DL", "2026-09-15", "Pavia", 28, 12,
     "The exam IS an upload: Colab notebook + PDF, on the day. Respect the assignment numbering exactly.", "2026-09-10"),
    ("509492", "Theoretical & Quantum Physics", "2026-09-22", "Statale", 30, 12,
     "Multiple choice per the archived mocks — format still unconfirmed by the lecturers.", "2026-09-17"),
    ("509488", "Text Mining and NLP", "2026-09-24", "Pavia", 30, 6,
     "Up to 32 points. WRONG CLOSED ANSWERS SCORE -0.5. Answer every open question; leave closed ones blank unless you can eliminate two options.", "2026-09-19"),
]

WINTER = [
    ("510109", "Probability and Statistical Inference", 52, 12, "The deepest archive you have: 20 published answer keys."),
    ("509478", "Knowledge Representation and Reasoning", 44, 12, "Final mark is the MEAN of the two modules; a strong module carries a weak one."),
    ("504464", "Organization Theory and Design", 45, 6, "8 tests x 30 MCQ in one sitting, +1/-1/0. To average 18 you need net +18 per section: ~22 right, 4 wrong, 4 blank."),
    ("510638", "Web and Social Media Search and Analysis", 38, 6, "Project + presentation + written. Mark split unverified."),
    ("509483", "Computational Logic", 30, 6, "294 published answer keys — the SMT-LIB encodings. Install z3 and run them."),
    ("509487", "Fuzzy Systems and Evolutionary Computing", 27, 6, "Questions recur with published model answers. Skip the optional project."),
    ("509493", "Statistical Modelling", 22, 6, "Six past exams extract cleanly. The lecture notes are image-only PDFs — readable, not searchable."),
    ("509498", "AI for Communication and Marketing", 16, 6, "85 solved MCQs cover the written half. Blocked until a lab window opens."),
]


def load_json(path: str, default):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def load_packs() -> dict[str, str]:
    packs = {}
    for path in Path("reference/packs").glob("*.md"):
        if path.stem == "README":
            continue
        packs[path.stem] = path.read_text()
    return packs


def load_drill() -> dict:
    banks = {}
    for path in sorted(Path("data/drill").glob("*.json")):
        bank = json.loads(path.read_text())
        cards = [
            {
                "topic": q["topic"], "seen": q["seen_in_papers"],
                "share": q["share_of_papers"], "marks": q["typical_marks"],
                "key": q["solution_key"], "text": q["statement"][:1200],
                "papers": q["papers"][:4],
            }
            for q in bank["question_types"] if q["seen_in_papers"] >= 2
        ]
        if cards:
            banks[path.stem] = {"name": bank.get("name", path.stem).title(), "cards": cards}
    return banks


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graduation cockpit</title>
<style>
:root{--bg:#fbfaf9;--fg:#191817;--dim:#6b6660;--line:#e2ded9;--card:#fff;--accent:#8a3f1e;--warn:#8a1e1e;--ok:#1e5f3a;--hl:#f5e4bd}
@media(prefers-color-scheme:dark){:root{--bg:#151413;--fg:#eceae7;--dim:#9b958d;--line:#2e2b28;--card:#1e1c1a;--accent:#e0864f;--warn:#e07070;--ok:#6dc494;--hl:#4a3c1e}}
:root[data-theme=dark]{--bg:#151413;--fg:#eceae7;--dim:#9b958d;--line:#2e2b28;--card:#1e1c1a;--accent:#e0864f;--warn:#e07070;--ok:#6dc494;--hl:#4a3c1e}
:root[data-theme=light]{--bg:#fbfaf9;--fg:#191817;--dim:#6b6660;--line:#e2ded9;--card:#fff;--accent:#8a3f1e;--warn:#8a1e1e;--ok:#1e5f3a;--hl:#f5e4bd}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}
.wrap{max-width:860px;margin:0 auto;padding:14px 14px 72px}
h1{font-size:1.3rem;margin:.2em 0 .1em}
h2{font-size:1.02rem;margin:1.5em 0 .5em}
.sub{color:var(--dim);font-size:.83rem;margin-bottom:1em}
nav{display:flex;gap:5px;position:sticky;top:0;background:var(--bg);padding:9px 0;border-bottom:1px solid var(--line);z-index:5;overflow-x:auto;-webkit-overflow-scrolling:touch}
nav button{flex:0 0 auto;padding:8px 12px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;font:inherit;font-size:.87rem;cursor:pointer;white-space:nowrap}
nav button[aria-selected=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
section{display:none}section.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:11px 13px;margin:9px 0}
.row{display:flex;justify-content:space-between;gap:10px;align-items:baseline;flex-wrap:wrap}
.big{font-size:1.85rem;font-weight:650;line-height:1.1}
.tag{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.gate{color:var(--warn);font-size:.86rem;margin-top:5px}
.meta{color:var(--dim);font-size:.81rem}
.done{opacity:.45}
table{width:100%;border-collapse:collapse;font-size:.86rem}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:600;font-size:.74rem;text-transform:uppercase;letter-spacing:.05em}
blockquote{margin:7px 0;padding:8px 11px;border-left:3px solid var(--accent);background:var(--bg);border-radius:0 6px 6px 0;font-size:.88rem;white-space:pre-wrap;word-break:break-word}
pre{white-space:pre-wrap;word-break:break-word;font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--bg);padding:10px;border-radius:7px;border:1px solid var(--line);max-height:65vh;overflow:auto}
select,input[type=search],button.act{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);max-width:100%}
input[type=search]{width:100%}
button.act{cursor:pointer}
.pill{display:inline-block;padding:1px 7px;border-radius:99px;border:1px solid var(--line);font-size:.73rem;color:var(--dim);margin:0 5px 4px 0}
.pill.p{border-color:var(--accent);color:var(--accent)}
.pill.s{border-color:var(--ok);color:var(--ok)}
.pill.w{border-color:var(--warn);color:var(--warn)}
.bar{height:5px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:7px}
.bar>i{display:block;height:100%;background:var(--accent)}
label.chk{display:flex;gap:9px;align-items:flex-start;cursor:pointer}
input[type=checkbox]{margin-top:5px;flex:none;width:17px;height:17px;accent-color:var(--accent)}
details>summary{cursor:pointer;font-weight:600;font-size:.92rem;padding:2px 0}
mark{background:var(--hl);color:inherit;padding:0 2px;border-radius:3px}
.opt{display:block;padding:7px 10px;margin:4px 0;border:1px solid var(--line);border-radius:7px;font-size:.9rem;cursor:pointer}
.opt.right{border-color:var(--ok);color:var(--ok)}
.opt.wrong{border-color:var(--warn);opacity:.6}
.md h1,.md h2,.md h3{font-size:1rem;margin:1em 0 .3em}
.md ol,.md ul{padding-left:20px;margin:.4em 0}
.md li{margin:.25em 0}
.md table{margin:.5em 0}
.mut{color:var(--dim);font-style:italic}
</style></head><body><div class="wrap">
<h1>Graduation cockpit</h1>
<div class="sub" id="sub"></div>
<nav id="nav"></nav>
<section id="today" class="on"></section>
<section id="exams"></section>
<section id="method"></section>
<section id="drill"></section>
<section id="questions"></section>
<section id="library"></section>
<section id="quiz"></section>
<section id="search"></section>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s);
const store={get:(k,d)=>{try{const v=localStorage.getItem('cockpit:'+k);return v==null?d:JSON.parse(v)}catch(e){return d}},
             set:(k,v)=>{try{localStorage.setItem('cockpit:'+k,JSON.stringify(v))}catch(e){}}};
const today=()=>new Date().toISOString().slice(0,10);
const days=(a,b)=>Math.round((new Date(a)-new Date(b))/864e5);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const cname=c=>(D.names[c]||(D.lib[c]&&D.lib[c].name)||c);

const TABS=[['today','Today'],['exams','Exams'],['method','Method'],['drill','Drill'],
            ['questions','Questions'],['library','Library'],['quiz','Quiz'],['search','Search']];
$('#nav').innerHTML=TABS.map(([id,label],i)=>
  '<button data-t="'+id+'" aria-selected="'+(i===0)+'">'+label+'</button>').join('');
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('#nav button').forEach(x=>x.setAttribute('aria-selected',x===b));
  document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id===b.dataset.t));
  window.scrollTo(0,0);
});

const next=D.exams.filter(e=>e.date>=today()).sort((a,b)=>a.date<b.date?-1:1);
$('#sub').textContent=D.built+' · '+D.stats;

/* ---------- Today ---------- */
function renderToday(){
  const t=today(), slots=D.calendar[t]||[], n=next[0];
  let h='';
  if(n){const d=days(n.date,t);
    h+='<div class="card"><div class="tag">next exam</div><div class="row"><div><div class="big">'+
      (d===0?'today':d+(d===1?' day':' days'))+'</div><div>'+esc(n.name)+'</div></div>'+
      '<div class="meta">'+n.date+'<br>'+esc(n.campus)+'</div></div>'+
      '<div class="gate">'+esc(n.gate)+'</div></div>';}
  const due=D.exams.filter(e=>e.book_by>=t&&days(e.book_by,t)<=4);
  if(due.length){h+='<div class="card"><div class="tag">booking closing</div>'+
    due.map(e=>'<div class="row"><span>'+esc(e.name)+'</span><span class="meta">book by '+e.book_by+'</span></div>').join('')+'</div>';}
  h+='<h2>Today&rsquo;s work</h2>';
  if(!slots.length){h+='<div class="card meta">Nothing scheduled — either before the plan starts or after the last exam.</div>';}
  else{const k='done:'+t, done=store.get(k,[]);
    h+='<div class="card">'+slots.map((s,i)=>
      '<label class="chk" style="margin:7px 0"><input type="checkbox" data-i="'+i+'"'+(done.includes(i)?' checked':'')+
      '><span><b>'+esc(cname(s[0]))+'</b> <span class="meta">'+s[1]+' h</span></span></label>').join('')+'</div>';}
  h+='<h2>The next fourteen days</h2><div class="card scroll"><table><tr><th>Date</th><th>h</th><th>Work</th></tr>'+
    Object.keys(D.calendar).filter(d=>d>=t).slice(0,14).map(d=>{
      const ex=D.exams.find(e=>e.date===d);
      const w=(D.calendar[d]||[]).map(s=>esc(cname(s[0]))+' '+s[1]+'h').join(', ')||'—';
      return '<tr><td>'+d.slice(5)+'</td><td>'+(D.calendar[d]||[]).reduce((a,s)=>a+s[1],0)+
        '</td><td>'+(ex?'<b>EXAM: '+esc(ex.name)+'</b><br>':'')+w+'</td></tr>';}).join('')+'</table></div>';
  $('#today').innerHTML=h;
  $('#today').querySelectorAll('input[type=checkbox]').forEach(c=>c.onchange=()=>{
    const k='done:'+today(); const s=new Set(store.get(k,[]));
    c.checked?s.add(+c.dataset.i):s.delete(+c.dataset.i); store.set(k,[...s]);});
}

/* ---------- Exams ---------- */
function renderExams(){
  let h='<h2>September</h2><div class="card scroll"><table><tr><th>Date</th><th>Course</th><th>Where</th><th>Book by</th><th>h</th><th>CFU</th></tr>'+
    D.exams.map(e=>'<tr'+(e.date<today()?' class="done"':'')+'><td>'+e.date.slice(5)+'</td><td>'+esc(e.name)+
      '</td><td>'+esc(e.campus)+'</td><td>'+e.book_by.slice(5)+'</td><td>'+e.hours+'</td><td>'+e.cfu+'</td></tr>').join('')+'</table></div>';
  h+=D.exams.map(e=>'<div class="card"><div class="row"><b>'+esc(e.name)+'</b><span class="meta">'+e.date+' · '+esc(e.campus)+
     '</span></div><div class="gate">'+esc(e.gate)+'</div></div>').join('');
  h+='<h2>January / February</h2>'+D.winter.map(w=>'<div class="card"><div class="row"><b>'+esc(w.name)+
    '</b><span class="meta">'+w.hours+' h · '+w.cfu+' CFU</span></div><div class="meta" style="margin-top:5px">'+esc(w.note)+'</div></div>').join('');
  h+='<div class="card meta">Winter dates are not published yet — Esse3 returns nothing for 2027.</div>';
  $('#exams').innerHTML=h;
}

/* ---------- Method (study packs) ---------- */
function md(src){
  const lines=src.split('\n');let out=[],inTable=false;
  for(let ln of lines){
    if(/^\|/.test(ln)){
      if(/^\|[\s\-:|]+\|$/.test(ln))continue;
      const cells=ln.split('|').slice(1,-1).map(c=>'<td>'+esc(c.trim())+'</td>').join('');
      if(!inTable){out.push('<div class="scroll"><table>');inTable=true;}
      out.push('<tr>'+cells+'</tr>');continue;
    }
    if(inTable){out.push('</table></div>');inTable=false;}
    if(/^#{1,3}\s/.test(ln))out.push('<h3>'+esc(ln.replace(/^#+\s/,''))+'</h3>');
    else if(/^\d+\.\s/.test(ln))out.push('<li>'+esc(ln.replace(/^\d+\.\s/,''))+'</li>');
    else if(/^[-*]\s/.test(ln))out.push('<li>'+esc(ln.replace(/^[-*]\s/,''))+'</li>');
    else if(ln.trim()==='')out.push('');
    else out.push('<p>'+esc(ln)+'</p>');
  }
  if(inTable)out.push('</table></div>');
  return out.join('\n').replace(/(<li>[\s\S]*?<\/li>\n?)+/g,m=>'<ul>'+m+'</ul>')
            .replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<code>$1</code>');
}
function renderMethod(){
  const codes=Object.keys(D.packs);
  $('#method').innerHTML='<div class="meta" style="margin:8px 0">Tap a course to open its study pack.</div>'+
    codes.map(c=>'<details class="card"><summary>'+esc(cname(c))+'</summary><div class="md">'+md(D.packs[c])+'</div></details>').join('');
}

/* ---------- Drill ---------- */
function renderDrill(){
  const codes=Object.keys(D.drill);
  if(!codes.length){$('#drill').innerHTML='<div class="card meta">No recurring question types were extracted.</div>';return;}
  $('#drill').innerHTML='<div class="card"><select id="pick">'+codes.map(c=>
    '<option value="'+c+'">'+esc(cname(c))+' ('+D.drill[c].cards.length+')</option>').join('')+'</select></div><div id="cards"></div>';
  const sel=store.get('course',codes[0]); $('#pick').value=codes.includes(sel)?sel:codes[0];
  $('#pick').onchange=e=>{store.set('course',e.target.value);cards()};
  cards();
  function cards(){
    const c=$('#pick').value, bank=D.drill[c];
    const k='drilled:'+c, done=new Set(store.get(k,[]));
    $('#cards').innerHTML='<div class="bar"><i style="width:'+Math.round(100*done.size/bank.cards.length)+'%"></i></div>'+
      '<div class="meta" style="margin:6px 0 2px">'+done.size+' of '+bank.cards.length+' worked</div>'+
      bank.cards.map((q,i)=>'<div class="card'+(done.has(i)?' done':'')+'">'+
        '<div><span class="pill p">'+esc(q.topic)+'</span><span class="pill">'+q.seen+' papers · '+Math.round(q.share*100)+'%</span>'+
        (q.marks?'<span class="pill">'+q.marks+' marks</span>':'')+'</div>'+
        '<blockquote>'+esc(q.text)+'</blockquote>'+
        (q.key?'<div class="meta">Worked solution: <b>'+esc(q.key)+'</b></div>':'<div class="meta">No published solution.</div>')+
        '<div class="meta">In: '+q.papers.map(esc).join(' · ')+'</div>'+
        '<label class="chk" style="margin-top:8px"><input type="checkbox" data-i="'+i+'"'+(done.has(i)?' checked':'')+'><span>worked it</span></label>'+
        '</div>').join('');
    $('#cards').querySelectorAll('input').forEach(x=>x.onchange=()=>{
      const s=new Set(store.get(k,[])); x.checked?s.add(+x.dataset.i):s.delete(+x.dataset.i);
      store.set(k,[...s]); cards();});
  }
}

/* ---------- Questions ---------- */
function renderQuestions(){
  const codes=Object.keys(D.lib).filter(c=>D.lib[c].questions.length);
  $('#questions').innerHTML='<div class="card"><select id="qpick">'+codes.map(c=>
    '<option value="'+c+'">'+esc(cname(c))+' ('+D.lib[c].questions.length+')</option>').join('')+
    '</select> <select id="qtopic"></select></div><div id="qlist"></div>';
  const p=$('#qpick'); p.value=codes.includes(store.get('qcourse'))?store.get('qcourse'):codes[0];
  p.onchange=()=>{store.set('qcourse',p.value);topics();list()};
  $('#qtopic').onchange=list; topics(); list();
  function topics(){
    const qs=D.lib[p.value].questions, t=[...new Set(qs.map(q=>q.topic))].sort();
    $('#qtopic').innerHTML='<option value="">all topics</option>'+t.map(x=>'<option>'+esc(x)+'</option>').join('');
  }
  function list(){
    const f=$('#qtopic').value;
    const qs=D.lib[p.value].questions.filter(q=>!f||q.topic===f);
    $('#qlist').innerHTML='<div class="meta" style="margin:8px 0">'+qs.length+' questions</div>'+qs.map(q=>
      '<div class="card"><div><span class="pill p">'+esc(q.topic)+'</span>'+
      (q.marks?'<span class="pill">'+q.marks+' marks</span>':'')+
      (q.mcq?'<span class="pill s">multiple choice</span>':'')+'</div>'+
      '<blockquote>'+esc(q.text)+'</blockquote>'+
      '<div class="meta">From: '+esc(q.paper)+'</div></div>').join('');
  }
}

/* ---------- Library ---------- */
function renderLibrary(){
  const codes=Object.keys(D.lib);
  $('#library').innerHTML='<div class="card"><select id="lpick">'+codes.map(c=>
    '<option value="'+c+'">'+esc(cname(c))+' ('+D.lib[c].documents.length+')</option>').join('')+'</select></div><div id="ldocs"></div>';
  const p=$('#lpick'); p.value=codes.includes(store.get('lcourse'))?store.get('lcourse'):codes[0];
  p.onchange=()=>{store.set('lcourse',p.value);docs()}; docs();
  function docs(){
    const ds=D.lib[p.value].documents.slice().sort((a,b)=>
      (a.role===b.role?b.chars-a.chars:['paper','solution','material','image-only','stub'].indexOf(a.role)-['paper','solution','material','image-only','stub'].indexOf(b.role)));
    const cls={paper:'p',solution:'s','image-only':'w',stub:'w',material:''};
    $('#ldocs').innerHTML=ds.map(d=>
      '<details class="card"><summary>'+esc(d.name)+'</summary>'+
      '<div style="margin:6px 0"><span class="pill '+(cls[d.role]||'')+'">'+d.role+'</span>'+
      '<span class="pill">'+d.kind+'</span><span class="pill">'+d.chars.toLocaleString()+' chars</span></div>'+
      (d.chars?'<pre>'+esc(d.text)+'</pre>'
              :'<div class="mut">No text layer — this PDF is an image export. Open it on disk:<br><code>'+esc(d.path)+'</code></div>')+
      '</details>').join('');
  }
}

/* ---------- Quiz ---------- */
function renderQuiz(){
  const banks=Object.keys(D.quiz);
  if(!banks.length){$('#quiz').innerHTML='<div class="card meta">No answer-keyed quiz bank is available.</div>';return;}
  $('#quiz').innerHTML='<div class="card"><select id="zpick">'+banks.map(b=>
    '<option value="'+b+'">'+esc(D.quiz[b].name)+' ('+D.quiz[b].items.length+')</option>').join('')+
    '</select> <button class="act" id="zreset">reset</button></div>'+
    '<div class="meta" style="margin:4px 0 0">'+esc(D.quiz[banks[0]].source)+'</div><div id="zlist"></div>';
  const p=$('#zpick'); p.onchange=list;
  $('#zreset').onclick=()=>{store.set('quiz:'+p.value,{});list()};
  list();
  function list(){
    const bank=D.quiz[p.value], state=store.get('quiz:'+p.value,{});
    const answered=Object.keys(state).length;
    const right=Object.values(state).filter(Boolean).length;
    $('#zlist').innerHTML='<div class="bar"><i style="width:'+Math.round(100*answered/bank.items.length)+'%"></i></div>'+
      '<div class="meta" style="margin:6px 0 2px">'+answered+' of '+bank.items.length+' answered · '+right+' correct</div>'+
      bank.items.map((q,i)=>{
        const shown=state[i]!==undefined;
        return '<div class="card"><div><span class="pill p">'+esc(q.topic)+'</span>'+
          (q.n?'<span class="pill">#'+q.n+'</span>':'')+'</div>'+
          '<div style="margin:6px 0 4px">'+esc(q.stem)+'</div>'+
          q.options.map((o,j)=>'<span class="opt'+(shown?(o.correct?' right':' wrong'):'')+
            '" data-q="'+i+'" data-o="'+j+'">'+esc(o.letter)+'. '+esc(o.text)+
            (shown&&o.correct?' ✓':'')+'</span>').join('')+'</div>';
      }).join('');
    $('#zlist').querySelectorAll('.opt').forEach(el=>el.onclick=()=>{
      const st=store.get('quiz:'+p.value,{}); const q=+el.dataset.q, o=+el.dataset.o;
      if(st[q]===undefined){st[q]=bank.items[q].options[o].correct;store.set('quiz:'+p.value,st);list();}
    });
  }
}

/* ---------- Search ---------- */
function renderSearch(){
  $('#search').innerHTML='<div class="card"><input type="search" id="sq" placeholder="search every document and question…"></div><div id="sres"></div>';
  let timer;
  $('#sq').oninput=()=>{clearTimeout(timer);timer=setTimeout(run,220)};
  function run(){
    const q=$('#sq').value.trim(); if(q.length<3){$('#sres').innerHTML='<div class="meta">Type at least three characters.</div>';return;}
    const rx=new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'ig');
    const out=[];
    for(const c of Object.keys(D.lib)){
      for(const d of D.lib[c].documents){
        if(!d.chars)continue;
        let m,n=0;rx.lastIndex=0;
        while((m=rx.exec(d.text))&&n<3){
          const s=Math.max(0,m.index-90),e=Math.min(d.text.length,m.index+140);
          out.push({c,doc:d.name,frag:d.text.slice(s,e)});n++;
          if(out.length>120)break;
        }
        if(out.length>120)break;
      }
      if(out.length>120)break;
    }
    $('#sres').innerHTML='<div class="meta" style="margin:8px 0">'+out.length+(out.length>120?'+':'')+' matches</div>'+
      out.map(r=>'<div class="card"><div class="meta">'+esc(cname(r.c))+' — '+esc(r.doc)+'</div>'+
        '<blockquote>'+esc(r.frag).replace(rx,m=>'<mark>'+m+'</mark>')+'</blockquote></div>').join('');
  }
}

renderToday();renderExams();renderMethod();renderDrill();renderQuestions();renderLibrary();renderQuiz();renderSearch();
</script></body></html>
"""


def main() -> int:
    library = load_json("data/library.json", {"courses": {}, "quiz_banks": {}})
    calendar = load_json("data/audit/calendar.json", {"days": {}})
    drill = load_drill()
    packs = load_packs()

    names = {c: v["name"].title() for c, v in library["courses"].items()}
    for code, name, *_ in EXAMS:
        names[code] = name
    for code, name, *_ in WINTER:
        names.setdefault(code, name)

    docs = sum(len(c["documents"]) for c in library["courses"].values())
    questions = sum(len(c["questions"]) for c in library["courses"].values())
    keys = sum(
        sum(1 for d in c["documents"] if d["role"] == "solution")
        for c in library["courses"].values()
    )
    mcqs = sum(len(b["items"]) for b in library["quiz_banks"].values())

    data = {
        "built": "built " + dt.date.today().isoformat(),
        "stats": (
            f"{docs} documents · {questions} questions · {keys} answer keys · "
            f"{mcqs} solved MCQs · offline"
        ),
        "names": names,
        "calendar": calendar.get("days", {}),
        "packs": packs,
        "exams": [
            {"code": c, "name": n, "date": d, "campus": camp,
             "hours": h, "cfu": cfu, "gate": g, "book_by": b}
            for c, n, d, camp, h, cfu, g, b in EXAMS
        ],
        "winter": [
            {"code": c, "name": n, "hours": h, "cfu": cfu, "note": note}
            for c, n, h, cfu, note in WINTER
        ],
        "drill": drill,
        "lib": library["courses"],
        "quiz": library["quiz_banks"],
    }

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.replace("__DATA__", payload))
    print(
        f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB) — {docs} documents, "
        f"{questions} questions, {keys} answer keys, {mcqs} solved MCQs, "
        f"{len(packs)} study packs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
