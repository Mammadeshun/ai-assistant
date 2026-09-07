# UniPV exam pack — prompt for a fresh Claude Code session

Paste everything below the line into a new session. It is written to be
self-contained: the connection details are exact and verified, and the facts
section stops the new session re-deriving things I already got wrong once.

---

## 0 · WHO AND WHEN

I am Mohammad Nouri Zadeh, matricola **537373**, on the interateneo BSc in
Artificial Intelligence (L-31) — administrative seat Pavia, jointly with Milano
Statale and Milano-Bicocca. Codice fiscale / Esse3 username `NRZMMM04T08Z224Z`.

**Today is 7 September 2026.** I have **passed nothing** and I have **sat
nothing** this session — I skipped the first five autumn appelli. Every one of
them has a second autumn sitting still ahead. Do not plan as though those exams
are gone.

I have 21 activities and 159 CFU left of 180. I am optimising for **18**, not
for a good mark. Never use my historical CFU/year rate as a scheduling input.
If you think something does not fit, express it as an **hours deficit with the
arithmetic shown** — do not tell me you "don't believe" a scenario.

---

## 1 · HOW TO CONNECT — read this before writing any code

Two authenticated sources, one identity provider.

| | |
|---|---|
| Esse3 | `https://studentionline.unipv.it` |
| Kiro (Moodle 4) | `https://elearning.unipv.it` |
| IdP | `https://unipv.idp.cineca.it` (Shibboleth SAML2, Cineca) |

**Credentials come from environment variables `UNIPV_USERNAME` and
`UNIPV_PASSWORD`.** Never hardcode them, never log them, never commit them. If
a library forces a file, write a gitignored `.env`, and add it to `.gitignore`
in the same commit.

### 1.1 Use one keep-alive connection — this is the whole ballgame

Two rules, and the second one cost me five weeks.

**Do not use a headless browser.** Playwright/Chromium fails in sandboxed
environments behind an egress proxy — every navigation dies with
`ERR_CONNECTION_RESET`, and with no X server it will not even launch.

**Do not use `urllib`.** Use `requests.Session` with a pooled adapter, or
anything else that keeps connections alive:

```python
import requests
http = requests.Session()
http.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) ... Chrome/120.0.0.0 Safari/537.36"
adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=0)
http.mount("https://", adapter)
```

Why it matters: **Shibboleth binds a service-provider session to the client IP
address** (`consistentAddress`, on by default). A sandbox that reaches the
internet through a proxy generally gets **a different source address on every
new TCP connection** — measure it and see:

```python
[requests.get("https://api.ipify.org").text for _ in range(4)]
# ['160.79.106.139', '160.79.106.132', '160.79.106.139', '160.79.106.129']  <- separate sessions
s = requests.Session()
[s.get("https://api.ipify.org").text for _ in range(4)]
# ['160.79.106.129', '160.79.106.129', '160.79.106.129', '160.79.106.129']  <- one session
```

`urllib` sends `Connection: close` on every request, so it opens a new
connection — and leaves from a new address — for every hop. The SP therefore
saw the request carrying its own freshly minted `_shibsession_` cookie arrive
from a stranger, discarded the session and restarted SSO.

**The failure looks exactly like a wrong password**, which is the trap: you land
back on the IdP login form with no error banner. Diagnose it by posting the
assertion with redirects disabled — if the SP answers `302` *and*
`Set-Cookie: _shibsession_...`, authentication is fine and you are losing the
session on the next request, not failing to get one. Only the connections to
the **SP** need a stable address; the IdP hops in between are irrelevant to it.

A pooled connection the far end closes is replaced by one on a new address, so
the same loss can recur mid-run. Detect the bounce (landing on
`idp.cineca.it` or `Logon.do`) and re-login rather than archiving a login page
as if it were the page you asked for.

### 1.2 The SSO chain, hop by hop

Request any protected page and follow the forms. Every hop is a form a browser
would auto-submit; submit them explicitly.

```
GET  https://studentionline.unipv.it/auth/studente/Libretto/LibrettoHome.do
 hop 0  relay page, no named forms        -> submit forms[0] as-is
 hop 1  routing form                      -> submit with the PASSWORD_FLOW fields
 hop 2  credential form (j_username/j_password) -> submit once
 hop 3  SAML assertion form               -> submit as-is, lands authenticated
```

**The routing step is the part that is easy to miss.** The IdP shows login-method
buttons (UNIPV / SPID). Its own `init.js` defines
`triggerFlow(flow, id, selectedFlow)`, and the UNIPV username/password button
calls `triggerFlow('Password', '', 'internal')`. So set these hidden fields:

```python
PASSWORD_FLOW = {
    "spid_idp": "",
    "auth_ctx": "authn/Password",
    "selected_flow": "internal",
}
```

The routing form is identifiable by `id="triggerFlow"` and a hidden input named
`_eventId_routing`.

**Since ~September 2026 the routing form and the credential form appear on the
same page.** If your code picks the credential form first it never triggers the
UNIPV flow. Submit routing first, once, then credentials.

### 1.3 Form parsing gotchas that cost me hours

- The submit control is `<button name="_eventId_proceed">`, **not** an `<input>`.
  A parser that only collects `<input>` elements drops the field the Spring
  Webflow needs and the POST silently does nothing. Collect `<button name=...>`
  too.
- Field names are `j_username` and `j_password`.
- **Make exactly one credential attempt per login.** If the credential form comes
  back a second time, stop and report — do not retry. A retry loop on a wrong
  password becomes an account lockout.

### 1.4 Kiro (Moodle 4) specifics

- Scrape `sesskey` from any logged-in page (`"sesskey":"..."`), then call
  `POST /lib/ajax/service.php?sesskey=<key>&info=core_course_get_enrolled_courses_by_timeline_classification`
  for the enrolled-course list.
- **Self-enrolment**: the form uses `instance` plus a `_qf__<id>_enrol_self_enrol_form`
  marker — *not* `enrolid`. Parse the whole quickform and resubmit it entire. On
  my account self-enrolment was open with no key; a parser looking for `enrolid`
  reports "not available" for every course and is simply wrong.
- **Folder contents are not on the folder page.** `mod/folder/view.php` lists
  `pluginfile.php` links; you must follow each one. My first crawl archived the
  folder pages and missed 166 files inside them.
- Several courses ship each exam sitting as a **zip**. Expand them — one course
  had its entire four-year archive inside 34 zips.
- Many lecture PDFs are **single-page image exports with no text layer**.
  `pypdf` and `pypdfium2` both return zero characters. Detect and OCR
  (`tesseract` + render via `pypdfium2`); do not silently drop them.

### 1.5 Esse3 specifics

- Appelli list: `/auth/studente/Appelli/AppelliF.do`
- My bookings: `/auth/studente/Appelli/BachecaPrenotazioni.do`
- Libretto: `/auth/studente/Libretto/LibrettoHome.do`
- Piano: `/auth/studente/Piani/PianoHome.do`
- **The appelli table's first cell is an empty icon column.** Reading it as the
  course name blanks every row and collapses 43 sittings into 21 unique dates.
  Take the course as the first cell that is neither empty nor a date.
- `Voto - Data Esame` is one combined column padded with zero-width spaces
  (`​`); strip them. Lode is written `30L` with no separator, so
  `\b(\d{1,2})\b` drops it — use `(?<!\d)(\d{1,2})(?!\d)`.
- The `iscrizione` field carries the real booking window: it opens **20 days**
  before the appello and closes **5 days** before. Do not assume.

### 1.6 Politeness and archiving — non-negotiable

- **Sequential. No concurrency. 2-second delay between every request.**
- **Save every raw response before parsing anything**: to
  `raw/<source>/<UTC timestamp>__<label>.<ext>`, with a `manifest.jsonl` line
  recording url, sha256, fetch time, HTTP status. Parse only from those files.
  I will want to re-parse many times; I do not want the servers hit again.

### 1.7 The credential works — do not go looking for a password problem

This was the open question for weeks and it is now settled. The password is
valid; the IdP issues a SAML assertion every time. What was broken was the
transport, described in §1.1. Verified working end to end on 7 September 2026:
Esse3 serves career, libretto, study plan, bookings and available sittings;
Kiro reaches Moodle with a live `sesskey` and lists 73 enrolled courses.

If a login probe fails, check in this order — the last item is the likely one:

1. Are `UNIPV_USERNAME` / `UNIPV_PASSWORD` actually set in the environment?
   (A scheduled watcher ran daily for five weeks doing nothing because they
   were not.)
2. Does the routing step still send `PASSWORD_FLOW`? (§1.2)
3. Are you keeping one connection alive across the whole chain? (§1.1)

**Still: exactly one credential attempt per login.** Never retry a rejected
password — that is how an account gets locked.

---

## 2 · FACTS ALREADY ESTABLISHED — verify, do not re-derive blind

Treat these as priors to confirm against live data, not as gospel. Each one cost
real work and two of them are corrections to my own earlier errors.

**Autumn 2026 appelli still ahead of me** (first sittings already missed):

| Exam | 2nd autumn sitting | Campus |
|---|---|---|
| Information Retrieval & RecSys | 15 Sep | Pavia |
| Ethics, Law and AI | 16 Sep | Pavia |
| Laboratory of Machine Learning | 21 Sep | Pavia |
| Data Mining | 24 Sep | Pavia |
| Brain Modelling | 25 Sep | Pavia |
| Cognitive Psychology | 8 Sep *(tomorrow)* or 25 Sep | **Bicocca** |
| Computer Programming | 9 Sep or 24 Sep | **Statale** |
| Calculus | 11 Sep or 25 Sep | Pavia |
| Machine Learning / ANN / DL | 15 Sep | Pavia |
| Theoretical & Quantum Physics | 22 Sep | **Statale** |
| Text Mining and NLP | 24 Sep | Pavia |

**These dates collide.** 15 Sep is both IR and ML; 24 Sep is Data Mining, Text
Mining and Computer Programming; 25 Sep is Brain Modelling, Cognitive Psychology
and Calculus. Solve this as a **bipartite matching** (course → available date)
and tell me the maximum number of exams that can physically be sat, and which
must be dropped. Do not hand-wave it.

**Pass gates — these lose marks when forgotten:**

- **Computer Programming** — two independent gates: theory ≥12/20 **and** code
  ≥6/10. Non-running code is an automatic fail.
- **Calculus** — Part 1 ≥15/30 on top of the overall 18, closed book. No
  Part1/Part2 split exists in autumn 2026.
- **Text Mining** — three parts; wrong closed answers score **−0.5**. Paper is
  out of 32, pass at 18, so blanks are affordable.
- **Cognitive Psychology** — compulsory oral as well as the written. The
  threshold drifts by course edition: on edition **7392** it is 12 and marks are
  summed; the current edition is 13. **Do not contact the lecturer (Bricolo)
  about the syllabus** — the course page says previous-year students must ask if
  they want the current rules, so silence keeps the lower threshold.
- **Machine Learning** — the exam *is* an upload: Colab notebook + PDF, on the
  day. Respect the assignment numbering exactly.
- **Organization Theory** — 8 tests × 30 MCQ in one sitting, +1/−1/0, final mark
  is the **average of the 8 sections**, so no section can be skipped. Net +18 per
  section ≈ 22 right / 4 wrong / 4 blank.
- **Brain Modelling** — coding project 30% + written 70%, and the project mark
  **carries across sittings of the same academic year**.
- **Data Mining** — the 12/30 of coursework was set during delivery and cannot be
  recovered; the written is sat for the full 30.

**Two corrections to earlier conclusions — do not repeat them:**

1. **Information Retrieval has a written exam**, not just a project. Two January
   past papers exist with full model answers. An earlier analysis called it
   project-only by misreading a forum post that literally says presentations
   happen "after the written exam".
2. **Quantum Physics module 2 is NOT multiple choice.** Module 1's mocks are MCQ;
   module 2 is short computational questions — expectation values under time
   evolution, reduced density matrices, purity, commutators, Bloch vectors,
   uncertainty relations. Budget accordingly.

**Blocked:** AI for Communication and Marketing (509498) — the compulsory lab
project gates the written exam and both 2026 submission windows closed with
nothing submitted. Check whether an autumn/winter window has opened.

**Unpublished:** winter 2027 appelli. Esse3 returned nothing for 2027 as of
1 August. Check again — if January dates now exist, that changes everything
about what can be deferred.

---

## 3 · PHASES

Work in order. **Stop after Phase 3 and wait for my approval** before generating
study material.

### PHASE 1 — COLLECT

Build:

```
unipv/
  raw/       one folder per course, untouched downloads
  data/      extracted JSON
  analysis/  scoring and plan
  output/    the PDFs I print
  tools/     your scripts
  logs/      what was fetched, what failed
```

This is **a script you write and run**, not agent browsing. Read only its summary
output. Never paste downloaded file contents into your context at this stage.

**From Esse3:** libretto (every exam passed and every one missing, with code, CFU,
date); piano di studi (remaining mandatory exams, remaining elective CFU, and
which electives are still open to me — a cheap elective can beat a hard
mandatory); total CFU to graduate; thesis and internship requirements;
propedeuticità chains; every remaining September appello per exam (date, time,
room, type, teacher, registration open/close, notes); and bookings I already
hold.

**From Kiro**, per candidate course, into `raw/<code>-<name>/`: slide decks,
lecture notes, handouts, textbook chapter lists; every past paper, mock, sample
question set and solution sheet, **including ones buried in forum posts and
"materiale vecchio" folders**; assignment and project specs with deadlines and
rubrics; every teacher message about exam format, "cosa portare all'esame", what
is excluded from this year's programme, and bonus points for homework or
attendance. Save section and module descriptions to `_course_text.html` — exam
announcements live there. List lecture recordings (count + total duration) but do
not download video.

**From my past-questions folder:** ask me for the path if I have not given it.
Inventory, merge with Kiro, de-duplicate by content hash.

**From the public syllabus** (unipv.it catalogue, "Programmi degli insegnamenti"):
official programme, CFU, hours, textbooks, declared exam modality. Cross-check
against Kiro. **When they disagree, flag the conflict and trust the teacher's most
recent Kiro message.**

Write `unipv/data/*.json` and a human-readable `unipv/analysis/inventory.md`.

### PHASE 2 — NORMALISE (scripts only)

Write and run `unipv/tools/extract.py`:

- Text-layer every PDF to `raw/<course>/_text/<file>.txt` via `pdftotext -layout`.
  Flag any PDF with <100 chars as **SCANNED** — OCR those (`ocrmypdf`) for past
  papers, skip it for slides.
- Extract figures at ≥200 DPI to `raw/<course>/_figures/` with PyMuPDF
  `get_images()`, **plus** a full-page 200 DPI render of any page with zero images
  but non-empty `page.get_drawings()` — that catches vector plots and diagrams.
  Write `_figures/index.json`:
  `{png, source_pdf, page, bbox, caption_guess}` where `caption_guess` is the
  nearest text line below the bbox.
- Classify every file as SLIDES / NOTES / PAST_PAPER / SOLUTIONS / ASSIGNMENT /
  ADMIN from filename regex and first-page text (`appello`, `prova d'esame`,
  `compito`, `soluzione`, `esercizio`, dates, `punti 8`) → `data/classified.json`.
- Split every PAST_PAPER into individual questions → `data/questions.jsonl`, one
  line each: `{course, source_file, exam_date, q_number, text, points, has_solution}`.

**Splitting is harder than it looks.** Papers in this degree use at least six
different formats and a single regex handles none of them well. Implement several
strategies and pick, per paper, whichever yields the most items:
`Exercise n` / `Question n`; bare-numbered multiple choice (`1 What is…` with
options `1. …` — punctuation is the only thing separating stem from option);
dotted parts `(1.1) (1.2)`; `1. [3 points] …`; imperative prompts with no
numbering at all (`Please describe…`, `Explain…`); and one-question-per-line
published question banks. A paper that yields exactly one "question" is a
splitter failure, not a one-question exam — report those rather than counting them.

Print a summary table only: `course | files | scanned | figures | past papers |
questions`. Do not print file contents.

### PHASE 3 — SCORE, THEN PLAN. **STOP FOR MY APPROVAL.**

Read `data/inventory.json`, `data/classified.json`, `data/questions.jsonl`, the
Esse3 JSON, and grep `_course_text.html`. **Measure, do not guess — every number
must come from a file you counted.**

`unipv/analysis/scoring.md`, one row per remaining exam I am eligible for:

| Field | How to derive it |
|---|---|
| CFU | Esse3 / syllabus |
| Material load | Real counts: decks, total slides, chapters, lectures, video hours |
| Exam format | scritto / orale / progetto / quiz + duration + open vs closed book |
| Predictability 1–5 | How much do past papers repeat? Count **distinct question archetypes** across every paper. 5 = the same 10 exercises rotate yearly; 1 = open-ended oral with no pattern. **Cite the count**: "8 of 9 papers ask the same 4 exercise types." If no archetype recurs in ≥2 papers, predictability is 1 **regardless** of how similar the papers look in aggregate. |
| Past-paper supply | # real papers, # with official solutions, year range |
| Prerequisite fit | Builds on exams I passed, or on ones I have not? |
| Pass mechanics | Minimum per section, mandatory oral after written, whether the oral can only lower or also raise, whether a project alone passes, whether midterm/homework bonuses still apply |
| Hours-to-18 | Range (low–high) + confidence L/M/H, **arithmetic shown** |
| Date & deadline | Appello date, registration close, days of runway from today |
| Risk flags | No past papers · oral-heavy · project >1 week · strict grading (only if evidenced in materials, never rumour) · **date clash** · travel to Milano |
| Cost-per-pass | Hours-to-18 ÷ P(pass). **Rank by this.** |

Then rank and print **Tier A** (take it) / **Tier B** (only if time holds) /
**Tier C** (skip, and why).

Then `unipv/analysis/PLAN.md`:

- The exact exam set to sit, ≤5 lines of reasoning each, and expected passes.
  **Solve the date-collision matching explicitly** and state the maximum feasible
  set.
- A day-by-day calendar from today to the last chosen appello, built **backwards**
  from exam dates. 30+ h/week, blocked by course. **No course may go more than 5
  days without contact before its exam** — carve spaced-review time out of study
  days rather than adding hours, and assert this in the generator. The last 48 h
  before each exam is past-paper drilling only. Include buffer days and one
  absorbed lost day per week.
- Sequencing logic: what to study when two exams are 3 days apart; which exam to
  sacrifice if I fall behind; explicit go/no-go checkpoints ("if by 16 Sep I
  cannot solve past paper X unaided, drop it and reallocate to Y").
- Registration checklist: every appello, its deadline, and where showing up and
  withdrawing (*ritiro*) is free — attempting a marginal exam is usually costless;
  say when it is.
- Rollover list for Jan–Feb 2027 and what to pre-build now (e.g. start a project).
- The exact file list you will generate in Phase 4, with page-count estimates.

**Stop here.**

### PHASE 4 — BUILD THE PRINTABLE PACK (after I approve)

Spawn **one subagent per course**. Each gets a clean context and reads only that
course's `_text/*.txt`, `_figures/index.json`, its rows of `questions.jsonl`, and
its `_course_text.html`. This is not a cost measure — one context holding four
courses of source material produces worse, more confused documents than four
clean ones. Collect their outputs and do the cross-course verification yourself.

Per chosen exam, into `unipv/output/`. **A4, designed for paper.**

**1. `PASS-ESSENTIALS_<course>.pdf`** — the minimum to reach 18. 15–30 pages.
Page 1 is an exam brief: format, duration, number and type of questions, scoring,
how many points make 18, what is allowed (formula sheet? calculator?), what the
teacher explicitly excluded this year, date/time/room. Then topic by topic,
ordered by how often each appears in past papers, **stating the frequency**
("appeared in 7/9 papers"). Each topic: the exact definition or statement, the
formula(s) verbatim in the original notation, the method as a numbered procedure,
one fully worked exam-style example. **Figures are mandatory where they exist** —
place the actual extracted PNGs, do not redraw, do not replace with prose, caption
each with its source (`[Lecture 4, slide 22]`). If a figure did not extract
cleanly, place the rendered full page rather than dropping it. End with a dense
one-page formula sheet, common traps / where marks are lost, and "if you only have
6 hours": the ranked minimum subset. Nothing that never appeared in an exam goes
in, unless it is needed to understand something that did.

**2. `PRACTICE_<course>.pdf`** — questions only, room to write. Pooled from real
past papers + my questions folder + your generated variants. Grouped by topic,
easy → hard, continuous numbering. **Blank ruled answer space after every
question**, sized to the answer: ~1/3 page short, a full page for derivations and
proofs, graph paper or a labelled empty axis box where the answer is a plot. Err
generous. Each question tagged with topic, estimated minutes, recurrence
(★★★ = every year). **No answers anywhere in this file.**

**3. `SOLUTIONS_<course>.pdf`** — separate file, same numbering. Full worked
solutions in the style the examiner expects, marking scheme where known, and one
line per question: "for a bare pass, this much is enough." Official solutions
quoted as-is and cited; yours clearly marked.

**4. `MOCK-EXAM_<course>.pdf` + `MOCK-EXAM_<course>_SOLUTIONS.pdf`** — one
realistic timed paper in the true format and duration, built from the recurring
archetypes, not a reshuffle of the practice set.

**5. `STUDY-PLAN.pdf`** — the Phase 3 calendar, printable, checkbox per study
session and per registration deadline.

**Typography:** A4 portrait, 2 cm margins, body ≥11 pt, pure black on white (no
dark blocks or background fills — printer ink), clear heading hierarchy, page
numbers, table of contents, each topic starts on a new page, no orphaned figures,
formulas as real math via LaTeX or Typst (never ASCII), tables never split across
pages.

Generate by **writing a script that consumes the JSON and emits LaTeX/Typst**. Do
not hand-author markup question by question.

### PHASE 5 — VERIFY BEFORE REPORTING DONE

Write `unipv/tools/verify.py`, run it, print results as a table.

- **Coverage** — every question archetype in `questions.jsonl` maps to a section
  of that course's PASS-ESSENTIALS. Report % and list uncovered archetypes by name.
- **Glyphs** — `pdffonts` on every output, flag non-embedded fonts. `pdftotext`
  every page, flag pages with 0 characters or containing U+FFFD / □.
- **Geometry** — `pdfinfo` confirms A4. Flag any page whose text bbox exceeds the
  margin box, any figure with zero area, any table spanning a page break.
- **Fidelity** — sample 5 formulas per course, diff character-by-character against
  the source text layer, report exact-match yes/no with the source line quoted.
- **Fabrication audit** — every PRACTICE question must carry
  `[PAST PAPER — <file>, <date>]` or `[GENERATED VARIANT]`. **Fail the build if any
  lacks one.** Grep all output for claims not traceable to a source; fix or tag.

Then rasterise and **actually look at**: page 1 of each PASS-ESSENTIALS, its
densest figure page, and one PRACTICE page per course. Do not rasterise the full
documents — hundreds of page images crowd out the source material you are checking
against.

Finish with: exams chosen, total pages to print, print order, and the three things
most likely to make this plan fail.

---

## 4 · GROUND RULES — these override everything above

- **Never invent academic content.** Everything in the material comes from Kiro,
  the syllabus, or my questions folder. Anything you infer is tagged
  `[NOT IN SOURCE — VERIFY]`.
- **Never present an invented question as real.** Real → `[PAST PAPER — <file>,
  <date>]`. Yours → `[GENERATED VARIANT]`.
- **Cite a file path or URL for every factual claim** about a course — format,
  load, deadline, grading.
- **Credentials never touch a log, plan, commit or chat message.** Environment
  variables only; if a file is unavoidable it is gitignored in the same commit.
- **If a portal page will not load or a course is locked, say so explicitly and
  mark it DATA INCOMPLETE.** Never fill a gap with a guess.
- **If you are blocked, tell me exactly what to click.** One retry, then ask.
- **Ask at most 5 clarifying questions**, and only where a wrong answer wastes
  real work. Otherwise proceed on your best assumption and label it.
- **Correct me.** If something here is wrong or a bad idea, say so plainly. I
  would rather be corrected than agreed with.
