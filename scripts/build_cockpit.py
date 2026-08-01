#!/usr/bin/env python3
"""Build the offline study cockpit: one self-contained HTML file.

Everything is inlined - no network, no CDN, no fonts - because the times you
most need it are on a train to Milan and in a corridor ten minutes before a
sitting. Progress is kept in localStorage on the device; nothing is uploaded.

Three views:
  Today   what the calendar says to work on, with a countdown to the next exam
  Exams   every sitting with its pass gate, campus, and booking deadline
  Drill   the recurring question types as flashcards, most-frequent first
"""

from __future__ import annotations

import datetime as dt
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path("data/cockpit.html")

EXAMS = [
    # code, name, date, campus, hours, cfu, gate, book_by
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
    ("510109", "Probability and Statistical Inference", 52, 12, "47 solved papers — the deepest archive you have."),
    ("509478", "Knowledge Representation and Reasoning", 44, 12, "Final mark is the MEAN of the two modules; a strong module carries a weak one."),
    ("504464", "Organization Theory and Design", 45, 6, "8 tests x 30 MCQ in one sitting, +1/-1/0. To average 18 you need net +18 per section: ~22 right, 4 wrong, 4 blank."),
    ("510638", "Web and Social Media Search and Analysis", 38, 6, "Project + presentation + written. Mark split unverified."),
    ("509483", "Computational Logic", 30, 6, "Solved assignments with the SMT-LIB encodings. Install z3 and run them."),
    ("509487", "Fuzzy Systems and Evolutionary Computing", 27, 6, "Questions recur near-verbatim with published model answers. Skip the optional project."),
    ("509493", "Statistical Modelling", 22, 6, "Material is on laura-dangelo.github.io, not Kiro. Esame1-6 plus solved exercise sets."),
    ("509498", "AI for Communication and Marketing", 16, 6, "85 solved MCQs cover the written half. Blocked until a lab window opens."),
]


def load_drill() -> dict:
    banks = {}
    for path in sorted(Path("data/drill").glob("*.json")):
        bank = json.loads(path.read_text())
        cards = [
            {
                "topic": q["topic"],
                "seen": q["seen_in_papers"],
                "share": q["share_of_papers"],
                "marks": q["typical_marks"],
                "key": q["solution_key"],
                "text": q["statement"][:900],
                "papers": q["papers"][:4],
            }
            for q in bank["question_types"]
            if q["seen_in_papers"] >= 2
        ]
        if cards:
            banks[path.stem] = {"name": bank.get("name", path.stem), "cards": cards}
    return banks


def load_calendar() -> dict:
    path = Path("data/audit/calendar.json")
    return json.loads(path.read_text()) if path.exists() else {"days": {}}


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graduation cockpit</title>
<style>
:root{--bg:#fbfaf9;--fg:#191817;--dim:#6b6660;--line:#e2ded9;--card:#fff;--accent:#8a3f1e;--warn:#8a1e1e;--ok:#1e5f3a}
@media(prefers-color-scheme:dark){:root{--bg:#151413;--fg:#eceae7;--dim:#9b958d;--line:#2e2b28;--card:#1e1c1a;--accent:#e0864f;--warn:#e07070;--ok:#6dc494}}
:root[data-theme=dark]{--bg:#151413;--fg:#eceae7;--dim:#9b958d;--line:#2e2b28;--card:#1e1c1a;--accent:#e0864f;--warn:#e07070;--ok:#6dc494}
:root[data-theme=light]{--bg:#fbfaf9;--fg:#191817;--dim:#6b6660;--line:#e2ded9;--card:#fff;--accent:#8a3f1e;--warn:#8a1e1e;--ok:#1e5f3a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}
.wrap{max-width:820px;margin:0 auto;padding:16px 16px 64px}
h1{font-size:1.35rem;margin:.2em 0 .1em}
h2{font-size:1.05rem;margin:1.6em 0 .5em;letter-spacing:.01em}
.sub{color:var(--dim);font-size:.85rem;margin-bottom:1.2em}
nav{display:flex;gap:6px;position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);z-index:5;flex-wrap:wrap}
nav button{flex:1 1 auto;min-width:88px;padding:9px 10px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;font:inherit;font-size:.9rem;cursor:pointer}
nav button[aria-selected=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
section{display:none}section.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.row{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
.big{font-size:1.9rem;font-weight:650;line-height:1.1}
.tag{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.gate{color:var(--warn);font-size:.87rem;margin-top:6px}
.meta{color:var(--dim);font-size:.83rem}
.done{opacity:.45}
table{width:100%;border-collapse:collapse;font-size:.88rem}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:600;font-size:.76rem;text-transform:uppercase;letter-spacing:.05em}
blockquote{margin:8px 0;padding:9px 12px;border-left:3px solid var(--accent);background:var(--bg);border-radius:0 6px 6px 0;font-size:.9rem;white-space:pre-wrap;word-break:break-word}
select,button.act{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
button.act{cursor:pointer}
.pill{display:inline-block;padding:1px 7px;border-radius:99px;border:1px solid var(--line);font-size:.75rem;color:var(--dim);margin-right:5px}
.bar{height:5px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:8px}
.bar>i{display:block;height:100%;background:var(--accent)}
label.chk{display:flex;gap:9px;align-items:flex-start;cursor:pointer}
input[type=checkbox]{margin-top:5px;flex:none;width:17px;height:17px;accent-color:var(--accent)}
</style></head><body><div class="wrap">
<h1>Graduation cockpit</h1>
<div class="sub" id="sub"></div>
<nav>
  <button data-t="today" aria-selected="true">Today</button>
  <button data-t="exams" aria-selected="false">Exams</button>
  <button data-t="drill" aria-selected="false">Drill</button>
  <button data-t="night" aria-selected="false">Night before</button>
</nav>
<section id="today" class="on"></section>
<section id="exams"></section>
<section id="drill"></section>
<section id="night"></section>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s);
const store={get:(k,d)=>{try{return JSON.parse(localStorage.getItem('cockpit:'+k))??d}catch(e){return d}},
             set:(k,v)=>localStorage.setItem('cockpit:'+k,JSON.stringify(v))};
const today=()=>new Date().toISOString().slice(0,10);
const days=(a,b)=>Math.round((new Date(a)-new Date(b))/864e5);
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('nav button').forEach(x=>x.setAttribute('aria-selected',x===b));
  document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',s.id===b.dataset.t));
});

const next=D.exams.filter(e=>e.date>=today()).sort((a,b)=>a.date<b.date?-1:1);
$('#sub').textContent=D.built+' · '+D.exams.length+' exams in September, '+D.winter.length+' in January/February';

function renderToday(){
  const t=today(), slots=D.calendar[t]||[];
  const n=next[0];
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
  else{const doneK='done:'+t, done=store.get(doneK,[]);
    h+='<div class="card">'+slots.map((s,i)=>{
      const nm=(D.names[s[0]]||s[0]);
      return '<label class="chk" style="margin:7px 0"><input type="checkbox" data-i="'+i+'"'+(done.includes(i)?' checked':'')+
        '><span><b>'+esc(nm)+'</b> <span class="meta">'+s[1]+' h</span></span></label>';}).join('')+'</div>';}
  h+='<h2>The next fourteen days</h2><div class="card scroll"><table><tr><th>Date</th><th>Hours</th><th>Work</th></tr>'+
    Object.keys(D.calendar).filter(d=>d>=t).slice(0,14).map(d=>{
      const ex=D.exams.find(e=>e.date===d);
      const w=(D.calendar[d]||[]).map(s=>esc(D.names[s[0]]||s[0])+' '+s[1]+'h').join(', ')||'—';
      return '<tr><td>'+d.slice(5)+'</td><td>'+(D.calendar[d]||[]).reduce((a,s)=>a+s[1],0)+
        '</td><td>'+(ex?'<b>EXAM: '+esc(ex.name)+'</b><br>':'')+w+'</td></tr>';}).join('')+'</table></div>';
  $('#today').innerHTML=h;
  $('#today').querySelectorAll('input[type=checkbox]').forEach(c=>c.onchange=()=>{
    const k='done:'+today(); const s=new Set(store.get(k,[]));
    c.checked?s.add(+c.dataset.i):s.delete(+c.dataset.i); store.set(k,[...s]); });
}

function renderExams(){
  let h='<h2>September</h2><div class="card scroll"><table><tr><th>Date</th><th>Course</th><th>Where</th><th>Book by</th><th>h</th><th>CFU</th></tr>'+
    D.exams.map(e=>'<tr'+(e.date<today()?' class="done"':'')+'><td>'+e.date.slice(5)+'</td><td>'+esc(e.name)+
      '</td><td>'+esc(e.campus)+'</td><td>'+e.book_by.slice(5)+'</td><td>'+e.hours+'</td><td>'+e.cfu+'</td></tr>').join('')+'</table></div>';
  h+=D.exams.map(e=>'<div class="card"><div class="row"><b>'+esc(e.name)+'</b><span class="meta">'+e.date+' · '+esc(e.campus)+'</span></div><div class="gate">'+esc(e.gate)+'</div></div>').join('');
  h+='<h2>January / February</h2>'+D.winter.map(w=>'<div class="card"><div class="row"><b>'+esc(w.name)+
    '</b><span class="meta">'+w.hours+' h · '+w.cfu+' CFU</span></div><div class="meta" style="margin-top:5px">'+esc(w.note)+'</div></div>').join('');
  h+='<div class="card meta">Winter dates are not published yet — Esse3 returns nothing for 2027.</div>';
  $('#exams').innerHTML=h;
}

function renderDrill(){
  const codes=Object.keys(D.drill);
  if(!codes.length){$('#drill').innerHTML='<div class="card meta">No drillable question types were extracted.</div>';return;}
  const sel=store.get('course',codes[0]);
  let h='<div class="card"><select id="pick">'+codes.map(c=>'<option value="'+c+'"'+(c===sel?' selected':'')+'>'+esc(D.drill[c].name)+' ('+D.drill[c].cards.length+')</option>').join('')+'</select></div><div id="cards"></div>';
  $('#drill').innerHTML=h;
  $('#pick').onchange=e=>{store.set('course',e.target.value);cards()};
  cards();
  function cards(){
    const c=store.get('course',codes[0]), bank=D.drill[c]||D.drill[codes[0]];
    const k='drilled:'+c, done=new Set(store.get(k,[]));
    $('#cards').innerHTML='<div class="bar"><i style="width:'+Math.round(100*done.size/bank.cards.length)+'%"></i></div>'+
      '<div class="meta" style="margin:6px 0 2px">'+done.size+' of '+bank.cards.length+' worked</div>'+
      bank.cards.map((q,i)=>'<div class="card'+(done.has(i)?' done':'')+'">'+
        '<div><span class="pill">'+esc(q.topic)+'</span><span class="pill">'+q.seen+' papers · '+Math.round(q.share*100)+'%</span>'+
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

function renderNight(){
  $('#night').innerHTML=D.exams.map(e=>{
    const b=D.drill[e.code];
    const top=b?b.cards.slice(0,6):[];
    return '<div class="card"><div class="row"><b>'+esc(e.name)+'</b><span class="meta">'+e.date+' · '+esc(e.campus)+'</span></div>'+
      '<div class="gate">'+esc(e.gate)+'</div>'+
      (top.length?'<div class="meta" style="margin-top:9px">Most likely to appear:</div><ol style="margin:5px 0 0;padding-left:20px">'+
        top.map(q=>'<li style="margin:3px 0">'+esc(q.topic)+' <span class="meta">('+q.seen+' papers)</span></li>').join('')+'</ol>'
       :'<div class="meta" style="margin-top:9px">No past papers archived — nothing to predict.</div>')+
      '</div>';}).join('');
}
renderToday();renderExams();renderDrill();renderNight();
</script></body></html>
"""


def main() -> int:
    drill = load_drill()
    calendar = load_calendar()

    names = {c: v["name"] for c, v in drill.items()}
    for code, name, *_ in EXAMS:
        names[code] = name

    data = {
        "built": "built " + dt.date.today().isoformat(),
        "names": names,
        "calendar": calendar.get("days", {}),
        "exams": [
            {
                "code": c, "name": n, "date": d, "campus": camp,
                "hours": h, "cfu": cfu, "gate": g, "book_by": b,
            }
            for c, n, d, camp, h, cfu, g, b in EXAMS
        ],
        "winter": [
            {"code": c, "name": n, "hours": h, "cfu": cfu, "note": note}
            for c, n, h, cfu, note in WINTER
        ],
        "drill": {
            c: {"name": v["name"].title(), "cards": v["cards"]} for c, v in drill.items()
        },
    }

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.replace("__DATA__", payload))
    cards = sum(len(v["cards"]) for v in drill.values())
    size = OUT.stat().st_size / 1024
    print(f"wrote {OUT} ({size:.0f} KB) — {len(drill)} courses, {cards} drill cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
