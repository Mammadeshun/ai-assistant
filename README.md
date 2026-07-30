# gradplan — earliest possible graduation session

Answers one question for the interateneo BSc in **Artificial Intelligence**
(L-31; Pavia, Milano Statale, Milano-Bicocca; administrative seat Pavia):

> What is the earliest academic session in which I can graduate?

It reads the career from Esse3, the enrolments from Kiro, and the rules and
calendars from the public course site, then works out which published
graduation session is actually reachable and what has to happen to hit it.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium     # skip if Chromium is already present
```

## Use

```bash
# 1. Public rules and calendars — no login.
python -m gradplan fetch-public

# 2. Your career. Pick the auth mode that suits you (see below).
python -m gradplan fetch-esse3 --auth interactive
python -m gradplan fetch-kiro  --auth storage

# 3. Parse the archive into data/career.json
python -m gradplan build-career

# 4. The answer
python -m gradplan plan --in-corso
```

You can get an answer before wiring up Esse3 by naming what you have left:

```bash
python -m gradplan plan --remaining "Statistical modelling,Brain modelling" --in-corso
```

## Authentication

Nothing is hardcoded and nothing is written to the repo. Three modes:

| Mode | What it does |
|---|---|
| `--auth interactive` | Opens a visible browser; you sign in yourself, including any 2FA. The tool never handles your password. Recommended for the first run. |
| `--auth storage` | Reuses the browser session saved by a previous run (`data/storage_state.json`, gitignored). No credentials involved. |
| `--auth env` | Fills the SSO form from `UNIPV_USERNAME` / `UNIPV_PASSWORD` in the environment. |

If a login does not reach an authenticated page, the failing page is archived
under `data/raw/debug/` so you can see what the SSO actually returned.

## Raw-first archiving

Every response — HTML, JSON, PDF — is written to
`data/raw/<source>/<UTC-timestamp>__<label>.<ext>` and appended to
`data/raw/manifest.jsonl` with its URL, status and SHA-256. **Parsers only ever
read from the archive.** Iterating on a parser therefore costs nothing and
never touches the university servers again:

```bash
python -m gradplan build-career     # re-parses the last archived pages
```

Requests are strictly sequential with a delay (`--delay`, default 2s). There is
no concurrency anywhere.

## How the answer is computed

A graduation session is reachable only if all of these hold:

1. its **application deadline** (one month before the day) is still ahead;
2. every outstanding exam has a published sitting early enough to be
   **recorded** by the **records deadline** (one week before the day);
3. the report can be finished and uploaded by that same deadline;
4. the credits add up to 180.

Rules and dates come from the *Final examination regulations* published on
`bai.unipv.it` and are re-read on every `fetch-public` — they are not baked
into the code. The one genuinely tunable assumption is how long
*verbalizzazione* takes:

```bash
--recording-lag-days 7    # default: assume a week between sitting and recording
--recording-lag-days 0    # optimistic: the mark is recorded the same day
```

This single number often decides between two sessions, so the report states
which sittings it picked and when each would need to be recorded. Check the
tight cases against your teachers rather than trusting the default.

The projected degree mark follows the regulations: base score = CFU-weighted
average of *graded* exams × 11/3, rounded; the board adds 0–7; +2 for
graduating in corso; cum laude needs ≥112 and a unanimous board. Pass/fail
activities (labs, stage, language) earn credits but are excluded from the
average.

### Which university an exam belongs to

Esse3 is used when it says. Otherwise it is inferred from the exam calendars:
the three sessions rotate between campuses, so a course examined *away* from
the hosting university is anchored to its own. Courses that always follow the
host are left `unknown` rather than guessed — `university_confidence` in
`career.json` records which of the three applies.

## Output

* `data/career.json` — every activity with name, CFU, mark, date, status
  (`passed` / `enrolled` / `not_yet_taken`), university, plus a summary
  (CFU earned, weighted average, base degree score).
* `data/graduation_plan.json` — every published session with its verdict,
  blockers, the sittings chosen, and the projected mark.

Both are gitignored: they are personal academic records.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

30 tests, all offline. The parser tests run against fixtures; the browser test
drives real Chromium against a local fake Esse3 (login form, redirect, cookie
gate) to exercise the scraping path end to end.

The Esse3 fixtures under `tests/fixtures/` are **synthetic** — modelled on the
Cineca Esse3 libretto markup, not captured from a live account. The parser
locates tables by header keywords (Italian and English) rather than by CSS
classes or column positions, and reports anything it cannot parse instead of
dropping it silently. Once you have archived a real libretto, re-run
`build-career` and check the diagnostics it prints.

## Sources

Rules and calendars are fetched from, and attributable to:

* Final examination regulations and graduation calendar a.y. 2025/26 — `bai.unipv.it`
* Exam session windows and per-course sitting dates — `bai.unipv.it`
* Piano di studio, Allegato n. 3 to the Regolamento L-AI — mirrored in
  `reference/study_plan_2025_26.json` with CFU, codes and SSD per activity
