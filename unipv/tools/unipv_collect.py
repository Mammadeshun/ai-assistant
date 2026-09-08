#!/usr/bin/env python3
"""Collect everything needed to plan and sit the remaining UniPV exams.

    python unipv_collect.py esse3      career, plan, appelli, bookings
    python unipv_collect.py kiro       course material, per candidate course
    python unipv_collect.py inventory  read what was collected, summarise

This is a script, not a browsing session. It writes files and prints counts;
it never returns document contents to its caller. Everything it downloads is
kept byte-for-byte under unipv/raw/ and logged to unipv/logs/, so any later
claim can be traced back to the file it came from.

Transport note: one pooled keep-alive connection for the whole run. Shibboleth
binds its session to the client IP and this container's proxy changes source
address on every new TCP connection, so a client that reconnects per request
loses the session immediately after login. See gradplan/sources/http_session.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bs4 import BeautifulSoup  # noqa: E402

from gradplan import config  # noqa: E402
from gradplan.archive import RawArchive  # noqa: E402
from gradplan.sources.http_session import http_session  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW, DATA, ANALYSIS, LOGS = ROOT / "raw", ROOT / "data", ROOT / "analysis", ROOT / "logs"
DELAY = 0.3

# Downloaded, but never opened by this script.
BINARY_EXT = {".pdf", ".zip", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".png",
              ".jpg", ".jpeg", ".gif", ".ipynb", ".py", ".txt", ".csv", ".md",
              ".smt2", ".tex", ".r", ".m", ".java", ".c", ".cpp", ".rar", ".7z"}
# Listed with a duration, never fetched.
MAX_LEVEL = 3
MAX_PAGES = 400
VIDEO_MODULES = ("kalvidres", "videofile", "hvp", "lti", "panopto", "url")


def log(stream: str, **fields) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    fields["at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with (LOGS / f"{stream}.jsonl").open("a") as handle:
        handle.write(json.dumps(fields, ensure_ascii=False) + "\n")


def slug(text: str, limit: int = 60) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-")[:limit] or "x"


def session():
    creds = config.Credentials.from_env()
    if creds is None:
        raise SystemExit(
            "UNIPV_USERNAME / UNIPV_PASSWORD are not set. Nothing was fetched."
        )
    return http_session(RawArchive(RAW / "_archive"), delay=DELAY)


# ---------------------------------------------------------------- esse3 -----
def text_of(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip("​ ")


def parse_libretto(html: str) -> list[dict]:
    """Every activity on the transcript, passed or not.

    A row carries a grade only once the exam has been recorded; the absence of
    one is what marks an exam as still to sit.
    """
    out = []
    for tr in BeautifulSoup(html, "lxml").select("tr"):
        cells = [text_of(td) for td in tr.select("td")]
        cells = [c for c in cells if c]
        if not cells:
            continue
        head = re.match(r"^(\d{6})\s*-\s*(.+)$", cells[0])
        if not head:
            continue
        grade = date = None
        for cell in cells[1:]:
            found = re.match(r"^(\d{1,2}|[A-Z]+)\s*-\s*(\d{2}/\d{2}/\d{4})$", cell)
            if found:
                grade, date = found.group(1), found.group(2)
        numbers = [c for c in cells[1:] if re.fullmatch(r"\d+", c)]
        out.append({
            "code": head.group(1),
            "name": head.group(2).strip(),
            "year_of_course": int(numbers[0]) if numbers else None,
            "cfu": int(numbers[1]) if len(numbers) > 1 else None,
            "grade": grade,
            "recorded": date,
            "passed": grade is not None,
        })
    return out


def parse_appelli(html: str) -> list[dict]:
    """The sittings on offer, with the detail link each row hangs off."""
    out = []
    for tr in BeautifulSoup(html, "lxml").select("tr"):
        cells = tr.select("td")
        if len(cells) < 7:
            continue
        values = [text_of(c) for c in cells]
        name = next((v for v in values[:3] if v and not re.match(r"^\d{2}/\d{2}", v)), "")
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", " ".join(values))
        if not name or not dates:
            continue
        link = tr.select_one('a[href*="DatiPrenotazioneAppello.do"]')
        out.append({
            "activity": name,
            "exam_date": dates[0],
            "booking_opens": dates[1] if len(dates) > 1 else None,
            "booking_closes": dates[2] if len(dates) > 2 else None,
            "attendance": values[-3] if len(values) > 3 else "",
            "enrolled": values[-1] if values[-1].isdigit() else None,
            "detail_url": link["href"] if link else None,
        })
    return out


def parse_bookings(html: str) -> list[dict]:
    """What is already booked. Cancellability is the field that matters."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [l.strip("​ ").strip() for l in soup.get_text("\n", strip=True).split("\n")]
    out = []
    for i, line in enumerate(lines):
        head = re.match(r"^(.+?) \[(\d{6})\]$", line)
        if not head:
            continue
        window = lines[i + 1:i + 45]
        date = next((w for w in window if re.fullmatch(r"\d{2}/\d{2}/\d{4}", w)), None)
        cancel = next((w for w in window if "cancellare" in w.lower()), "")
        booked_on = None
        for j, w in enumerate(window):
            if w.startswith("Data Prenotazione"):
                booked_on = next((x for x in window[j:j + 3]
                                  if re.fullmatch(r"\d{2}/\d{2}/\d{4}", x)), None)
        out.append({
            "code": head.group(2),
            "name": head.group(1),
            "exam_date": date,
            "partial": any("parziale" in w.lower() for w in window[:6]),
            "booked_on": booked_on,
            "cancellable": not cancel,
            "cancel_note": cancel,
        })
    return out


# Esse3 renders an appello as a label/value list. A field with no value is
# still rendered as a label, so "take the next line" silently reads the next
# label as the value - which is how "Ora" came back as "Edificio e Aula".
APPELLO_LABELS = (
    "Ora", "Edificio", "Aula", "Indirizzo Edificio", "Docenti", "Note", "Tipo",
    "Descrizione", "Sessioni", "Numero Iscrizione", "Data Prenotazione",
    "Riservato per", "Svolgimento esame", "Partizionamento", "Data appello",
    "Tipo esame", "Periodo", "Cancella Prenotazione", "Stampa prenotazione",
)


def appello_fields(markup: str) -> dict[str, str]:
    """Label -> value, where a value may span several lines (several teachers)
    or be absent entirely."""
    soup = BeautifulSoup(markup, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [l.strip("\u200b ").strip()
             for l in soup.get_text("\n", strip=True).split("\n")]
    lines = [l for l in lines if l]
    labels = set(APPELLO_LABELS)
    values: dict[str, list[str]] = {}
    current = None
    for line in lines:
        # "Note appello", "Note per il docente" and friends are labels too, and
        # not listing them let them run on into whatever field came before.
        if line.startswith("Note") or line.startswith("Iscrizione"):
            current = "Note" if line.startswith("Note") else None
            values.setdefault("Note", [])
            continue
        if line in labels:
            current = line
            values.setdefault(current, [])
        elif current is not None:
            values[current].append(line)
            if len(values[current]) > 6:
                current = None
    # Docenti is a list of names; everything after it on the page is a summary
    # table. Keeping only entries that look like a name stops the run-on
    # without having to enumerate every label Esse3 might render next.
    teacher = re.compile(r"^[A-ZÀ-ÜÖ'’\- ]{4,}(?:\s*\([^)]+\))?$")
    people = []
    for entry in values.get("Docenti", []):
        if not teacher.match(entry):
            break
        people.append(entry)
    values["Docenti"] = people
    joined = {k: ", ".join(v) for k, v in values.items()}
    return {
        "time": joined.get("Ora", ""),
        "room": ", ".join(x for x in (joined.get("Edificio", ""),
                                      joined.get("Aula", "")) if x),
        "type": joined.get("Tipo esame") or joined.get("Tipo", ""),
        "teachers": joined.get("Docenti", ""),
        "notes": joined.get("Note", ""),
        "description": joined.get("Descrizione", ""),
    }


def collect_esse3() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    (RAW / "_esse3").mkdir(parents=True, exist_ok=True)
    handle = session()
    handle.login(config.ESSE3_LIBRETTO, success_marker="LibrettoHome")

    # URLs taken from the live navigation menu, not guessed. config's
    # ESSE3_STUDY_PLAN and ESSE3_CAREER are both 404s on this account: the
    # study plan is PianiHome.do (plural), and "Carriera" in the menu simply
    # points back at the libretto - there is no separate career page.
    base = config.ESSE3_BASE + "/auth/studente/"
    pages = {
        "libretto": config.ESSE3_LIBRETTO,
        "study_plan": base + "Piani/PianiHome.do",
        "career_acts": base + "Carriera/AttiCarriera.do",
        "bookings": config.ESSE3_EXAM_ENROLLMENTS,
        "appelli": config.ESSE3_AVAILABLE_EXAMS,
        "results_board": base + "Appelli/BachecaEsiti.do",
        "graduation": base + "Graduation/Bacheca.do",
        "internships": base + "tirocini/TiroHomeStudente.do",
    }
    saved: dict[str, str] = {}
    for name, url in pages.items():
        handle.goto(url, source="esse3", label=name)
        body = handle.content
        target = RAW / "_esse3" / f"{name}.html"
        target.write_text(body)
        saved[name] = body
        incomplete = "Pagina non trovata" in body or len(body) < 15000
        log("esse3", page=name, url=url, bytes=len(body), incomplete=incomplete)
        print(f"  {name:<12} {len(body):>7} bytes"
              + ("   DATA INCOMPLETE - Esse3 served a message page" if incomplete else ""))

    libretto = parse_libretto(saved["libretto"])
    appelli = parse_appelli(saved["appelli"])
    bookings = parse_bookings(saved["bookings"])

    # Each sitting's detail page: time, room, teacher, notes. The list view has
    # none of that, and 'which room, what time' is what you need on the day.
    details: dict[str, dict] = {}
    for row in appelli:
        if not row["detail_url"]:
            continue
        url = urllib.parse.urljoin(config.ESSE3_BASE + "/", row["detail_url"])
        key = slug(f"{row['activity']}-{row['exam_date']}")
        try:
            handle.goto(url, source="esse3", label=f"appello-{key}")
        except Exception as exc:  # noqa: BLE001
            log("esse3", detail=key, error=repr(exc))
            continue
        (RAW / "_esse3" / f"appello-{key}.html").write_text(handle.content)
        details[key] = {**appello_fields(handle.content),
                        "raw_file": f"raw/_esse3/appello-{key}.html"}
        row["detail"] = details[key]
        time.sleep(DELAY)
    handle.close()

    remaining = [a for a in libretto if not a["passed"]]
    payload = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "student": {"matricola": "537373"},
        "libretto": libretto,
        "passed": [a for a in libretto if a["passed"]],
        "remaining": remaining,
        "cfu_passed": sum(a["cfu"] or 0 for a in libretto if a["passed"]),
        "cfu_remaining": sum(a["cfu"] or 0 for a in remaining),
        "cfu_required": config.TOTAL_CFU_REQUIRED,
        "appelli": appelli,
        "bookings": bookings,
        "sources": {k: f"raw/_esse3/{k}.html" for k in pages},
    }
    (DATA / "esse3.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"\n  passed {len(payload['passed'])} ({payload['cfu_passed']} CFU), "
          f"remaining {len(remaining)} ({payload['cfu_remaining']} CFU), "
          f"{len(appelli)} sittings, {len(bookings)} bookings, "
          f"{len(details)} detail pages")
    print(f"  wrote {DATA/'esse3.json'}")
    return 0


# ----------------------------------------------------------------- kiro -----
CODE = re.compile(r"\b(5\d{5}|504\d{3}|510\d{3})\b")


def course_code(fullname: str, wanted: set[str] | None = None) -> str | None:
    """The Esse3 code a Kiro course belongs to.

    Usually the name simply starts with it: '509495 - DATA MINING - PROF...'.
    But a course split into modules is published under its own sub-codes with
    the parent in parentheses:

        '509479 - KNOWLEDGE REPRESENTATION AND REASONING - MOD. 1 ( 509478 - ...'

    Taking the first code found returns 509479, which is not an exam on the
    transcript, so the whole 12 CFU course was dropped from the crawl without
    a word. Match every code in the name against the ones actually wanted, and
    prefer a match over position.
    """
    codes = CODE.findall(fullname)
    if not codes:
        return None
    if wanted:
        for code in codes:
            if code in wanted:
                return code
    return codes[0]


def sesskey(markup: str) -> str | None:
    found = re.search(r'"sesskey":"([^"]+)"', markup)
    return found.group(1) if found else None


def enrolled_courses(handle) -> list[dict]:
    key = sesskey(handle.content)
    if not key:
        raise SystemExit("No sesskey on the Kiro landing page; not logged in.")
    url = (f"{config.KIRO_COURSES_API}?sesskey={key}"
           "&info=core_course_get_enrolled_courses_by_timeline_classification")
    record = handle.post_json(
        url,
        [{"index": 0,
          "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
          "args": {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname"}}],
        source="kiro", label="enrolled-courses",
    )
    payload = json.loads((RAW / "_archive" / record.path).read_text())
    return payload[0]["data"]["courses"]


def download(handle, url: str, target: Path) -> tuple[bool, int]:
    """Fetch one file to disk. Returns (fetched, bytes); never returns content."""
    if target.exists() and target.stat().st_size > 0:
        return False, target.stat().st_size
    try:
        response = handle._send("GET", url)
    except Exception as exc:  # noqa: BLE001
        log("kiro", url=url, error=repr(exc))
        return False, 0
    if response.status_code != 200 or not response.content:
        log("kiro", url=url, status=response.status_code, empty=True)
        return False, 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    log("kiro", url=url, path=str(target.relative_to(ROOT)), bytes=len(response.content),
        sha256=hashlib.sha256(response.content).hexdigest())
    time.sleep(DELAY)
    return True, len(response.content)


def filename_from(url: str, fallback: str) -> str:
    name = urllib.parse.unquote(url.split("?")[0].rsplit("/", 1)[-1])
    name = re.sub(r"[^0-9A-Za-z._ -]+", "_", name).strip()
    return name if name and "." in name else fallback


def collect_course(handle, course: dict, folder: Path) -> dict:
    """Everything reachable inside one Kiro course.

    Follows the three places material actually hides: resource stubs that
    redirect to the file, folder pages that list their contents rather than
    linking them from the course page, and forum threads where the exam-format
    announcements live.
    """
    stats = {"pages": 0, "files": 0, "bytes": 0, "forums": 0, "folders": 0,
             "assignments": 0, "quizzes": 0, "videos": [], "failed": 0}
    seen: set[str] = set()
    view = f"{config.KIRO_BASE}/course/view.php?id={course['id']}"
    try:
        handle.goto(view, source="kiro", label=f"course-{course['id']}")
    except Exception as exc:  # noqa: BLE001
        log("kiro", course=course["id"], error=repr(exc))
        stats["failed"] += 1
        return stats
    # Section and module descriptions - exam announcements live here.
    (folder / "_course_text.html").write_text(handle.content)
    stats["pages"] += 1

    # Breadth-first over the course. MAX_LEVEL bounds how far from the course
    # page we follow (course -> folder -> its files is two), MAX_PAGES bounds
    # the total so a forum with hundreds of threads cannot run away.
    queue = [(handle.content, view, 0)]
    walked = 0
    while queue and walked < MAX_PAGES:
        markup, base, level = queue.pop(0)
        walked += 1
        if level >= MAX_LEVEL:
            continue
        soup = BeautifulSoup(markup, "lxml")
        for anchor in soup.select("a[href]"):
            href = urllib.parse.urljoin(base, anchor["href"])
            if config.KIRO_BASE not in href:
                continue
            # Moodle addresses every activity as /mod/<kind>/view.php?id=N, so
            # the path alone is the same key for all of them - deduplicating on
            # it collapsed 27 resources into one. Keep the query for activities;
            # drop it for pluginfile URLs, where it is only an access token.
            key = href.split("?")[0] if "pluginfile.php" in href else href
            if key in seen:
                continue
            seen.add(key)
            label = text_of(anchor)[:80]

            if "pluginfile.php" in href:
                ext = Path(href.split("?")[0]).suffix.lower()
                if ext not in BINARY_EXT:
                    continue
                name = filename_from(href, f"file-{len(seen)}{ext}")
                got, size = download(handle, href, folder / name)
                stats["files"] += got
                stats["bytes"] += size if got else 0
                continue

            # Moodle renders a language switcher and a contacts/messaging
            # drawer on every page, and following them produced 7873 duplicate
            # renderings of the same pages in eight languages.
            if re.search(r"[?&]lang=|/message/|/user/contactsis|#", href):
                continue
            module = re.search(r"/mod/(\w+)/view\.php", href)
            if not module:
                continue
            kind = module.group(1)

            if kind in VIDEO_MODULES:
                # Listed, never downloaded.
                stats["videos"].append({"title": label, "url": href, "kind": kind})
                continue

            if kind in ("resource", "folder", "page", "forum", "assign", "quiz", "book"):
                try:
                    handle.goto(href, source="kiro", label=f"mod-{kind}-{len(seen)}")
                except Exception as exc:  # noqa: BLE001
                    log("kiro", url=href, error=repr(exc))
                    stats["failed"] += 1
                    continue
                body = handle.content
                stats["pages"] += 1
                mid = (re.search(r"id=(\d+)", href) or [None, str(len(seen))])[1]
                out = folder / "_pages" / f"{kind}-{mid}-{slug(label, 40)}.html"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(body)
                if kind == "folder":
                    stats["folders"] += 1
                    queue.append((body, href, level + 1))   # its files are inside
                elif kind == "forum":
                    stats["forums"] += 1
                    queue.append((body, href, level + 1))   # discussion threads
                elif kind == "assign":
                    stats["assignments"] += 1
                    queue.append((body, href, level + 1))   # spec attachments
                elif kind == "quiz":
                    stats["quizzes"] += 1
                elif kind == "resource":
                    # A resource stub redirects to the file itself.
                    if "pluginfile.php" in handle.url:
                        name = filename_from(handle.url, f"{slug(label)}.pdf")
                        got, size = download(handle, handle.url, folder / name)
                        stats["files"] += got
                        stats["bytes"] += size if got else 0
                    else:
                        # Some resource views embed the file rather than
                        # redirecting to it; the link is inside the page.
                        for tag in BeautifulSoup(body, "lxml").select(
                                'a[href*="pluginfile.php"], object[data*="pluginfile.php"]'):
                            direct = tag.get("href") or tag.get("data")
                            if Path(direct.split("?")[0]).suffix.lower() in BINARY_EXT:
                                name = filename_from(direct, f"{slug(label)}.pdf")
                                got, size = download(handle, direct, folder / name)
                                stats["files"] += got
                                stats["bytes"] += size if got else 0
                # No sleep here: goto() already waited self.delay.

            elif "/mod/forum/discuss.php" in href:
                try:
                    handle.goto(href, source="kiro", label=f"thread-{len(seen)}")
                    out = folder / "_pages" / f"thread-{slug(label)}.html"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(handle.content)
                    stats["pages"] += 1
                    queue.append((handle.content, href, level + 1))
                except Exception as exc:  # noqa: BLE001
                    log("kiro", url=href, error=repr(exc))
                    stats["failed"] += 1
    return stats


def collect_kiro(only: list[str] | None) -> int:
    esse3 = DATA / "esse3.json"
    if not esse3.exists():
        raise SystemExit("Run `unipv_collect.py esse3` first - it defines what is remaining.")
    remaining = {a["code"]: a["name"] for a in json.loads(esse3.read_text())["remaining"]}
    if only:
        remaining = {k: v for k, v in remaining.items() if k in only}

    handle = session()
    handle.login(config.KIRO_SAML_LOGIN, success_marker="elearning.unipv.it")
    courses = enrolled_courses(handle)
    print(f"  {len(courses)} enrolled Kiro courses; {len(remaining)} exams still to sit")

    # A course can have several editions; keep them all - old editions are
    # where 'materiale vecchio' and past papers survive, and on this degree
    # the assessment rules that apply are the ones for the student's own
    # cohort, not the newest edition.
    by_code: dict[str, list[dict]] = {}
    for course in courses:
        code = course_code(course["fullname"], set(remaining))
        if code in remaining:
            by_code.setdefault(code, []).append(course)

    # Crawl in booking-deadline order, not code order. The crawl takes hours;
    # if it is cut short, what should already be on disk is the material for
    # the exams that have to be booked first.
    payload = json.loads(esse3.read_text())
    deadline: dict[str, str] = {}
    for row in payload["appelli"]:
        for activity in payload["remaining"]:
            if activity["name"].strip().upper() == row["activity"].strip().upper():
                closes = row.get("booking_closes") or "31/12/2099"
                day, month, year = closes.split("/")
                key = f"{year}{month}{day}"
                if activity["code"] not in deadline or key < deadline[activity["code"]]:
                    deadline[activity["code"]] = key
    order = sorted(by_code, key=lambda c: (deadline.get(c, "99999999"), c))
    print("  order (by booking deadline): "
          + ", ".join(f"{c}:{deadline.get(c,'-')[4:]}" for c in order))

    missing = sorted(set(remaining) - set(by_code))
    summary = {}
    for code in order:
        name = remaining[code]
        folder = RAW / f"{code}-{slug(name, 40)}"
        folder.mkdir(parents=True, exist_ok=True)
        totals = {"editions": len(by_code[code]), "pages": 0, "files": 0, "bytes": 0,
                  "forums": 0, "folders": 0, "assignments": 0, "quizzes": 0,
                  "videos": 0, "failed": 0}
        for course in by_code[code]:
            sub = folder / slug(course["shortname"], 40)
            sub.mkdir(parents=True, exist_ok=True)
            stats = collect_course(handle, course, sub)
            (sub / "_meta.json").write_text(json.dumps(
                {"id": course["id"], "shortname": course["shortname"],
                 "fullname": course["fullname"], "url": course.get("viewurl"),
                 "videos": stats["videos"], "stats": {k: v for k, v in stats.items()
                                                      if k != "videos"}},
                indent=1, ensure_ascii=False))
            for key in totals:
                if key == "editions":
                    continue
                totals[key] += len(stats["videos"]) if key == "videos" else stats[key]
            print(f"    {code} {course['shortname'][:28]:<28} "
                  f"files={stats['files']:>3} pages={stats['pages']:>3} "
                  f"video={len(stats['videos']):>2} fail={stats['failed']}")
        summary[code] = {"name": name, **totals}

    handle.close()
    for code in missing:
        summary[code] = {"name": remaining[code], "DATA_INCOMPLETE":
                         "no Kiro course found for this code among enrolments"}
        print(f"    {code} {remaining[code][:34]:<34} DATA INCOMPLETE - no Kiro course")
    (DATA / "kiro_collection.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"\n  wrote {DATA/'kiro_collection.json'}")
    return 0


# ------------------------------------------------------------- discover -----
def search_courses(handle, term: str) -> list[dict]:
    """Every Kiro course matching a term, enrolled or not.

    The enrolled-courses API only lists what the student is already in, so a
    course they were never enrolled on is invisible to it - which is exactly
    the case that makes a course look like it has no material.
    """
    url = f"{config.KIRO_BASE}/course/search.php?search={urllib.parse.quote(term)}&perpage=100"
    try:
        handle.goto(url, source="kiro", label=f"search-{term}")
    except Exception as exc:  # noqa: BLE001
        log("discover", term=term, error=repr(exc))
        return []
    out, seen = [], set()
    soup = BeautifulSoup(handle.content, "lxml")
    for anchor in soup.select('a[href*="/course/view.php?id="]'):
        found = re.search(r"id=(\d+)", anchor["href"])
        if not found or found.group(1) in seen:
            continue
        seen.add(found.group(1))
        out.append({"id": found.group(1), "fullname": text_of(anchor)})
    return out


def collect_discover(only: list[str] | None, enrol: bool) -> int:
    """Find every edition of every remaining exam, and enrol where open.

    A course with no downloadable material is ambiguous: it may genuinely
    publish nothing, or the student may simply not be enrolled on that edition.
    Searching separates the two, and self-enrolment resolves the second.
    """
    esse3 = json.loads((DATA / "esse3.json").read_text())
    remaining = {a["code"]: a["name"] for a in esse3["remaining"]}
    if only:
        remaining = {k: v for k, v in remaining.items() if k in only}

    handle = session()
    handle.login(config.KIRO_SAML_LOGIN, success_marker="elearning.unipv.it")
    enrolled = {str(c["id"]): c for c in enrolled_courses(handle)}
    print(f"  enrolled in {len(enrolled)} courses; searching {len(remaining)} codes")

    from gradplan.sources.kiro import self_enrol

    report: dict[str, dict] = {}
    for code in sorted(remaining):
        editions = search_courses(handle, code)
        rows = []
        for edition in editions:
            if code not in edition["fullname"] and code not in edition["id"]:
                # The search is fuzzy; keep only courses whose name carries the code.
                if not re.search(rf"\b{code}\b", edition["fullname"]):
                    continue
            state = "enrolled" if edition["id"] in enrolled else "not-enrolled"
            if state == "not-enrolled" and enrol:
                try:
                    state = self_enrol(handle, edition["id"])
                except Exception as exc:  # noqa: BLE001
                    state = f"failed:{type(exc).__name__}"
                log("discover", code=code, course=edition["id"], result=state)
            rows.append({"id": edition["id"], "name": edition["fullname"], "state": state})
        report[code] = {"name": remaining[code], "editions": rows}
        gained = sum(1 for r in rows if r["state"] == "enrolled" and r["id"] not in enrolled)
        print(f"    {code} {remaining[code][:34]:<36} found={len(rows):>2} "
              + " ".join(sorted({r["state"] for r in rows})) 
              + (f"  (+{gained} new)" if gained else ""))
    handle.close()
    (DATA / "kiro_editions.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    newly = [c for c, v in report.items()
             if any(r["state"] == "enrolled" for r in v["editions"])]
    print(f"\n  wrote {DATA/'kiro_editions.json'}")
    print(f"  codes with at least one enrolled edition: {len(newly)}/{len(report)}")
    blocked = {c: [r for r in v["editions"] if r["state"] in ("needs-key", "no-self-enrolment")]
               for c, v in report.items()}
    blocked = {c: v for c, v in blocked.items() if v}
    if blocked:
        print("  enrolment not open (needs a key, or self-enrolment disabled):")
        for code, rows in blocked.items():
            for row in rows:
                print(f"    {code} course {row['id']} {row['name'][:44]} -> {row['state']}")
    return 0


# ------------------------------------------------------------- syllabus -----
CATALOGUE = "https://unipv.coursecatalogue.cineca.it/api/v1"


def collect_syllabus() -> int:
    """The official course catalogue, for cross-checking Kiro.

    Cineca serves the catalogue as an Angular app whose per-course syllabus
    endpoint is not reachable from outside the browser - Chromium cannot cross
    this container's proxy, so the declared exam modality and reading lists are
    marked DATA INCOMPLETE rather than invented. What /corsi does give is
    authoritative and worth having: official CFU, taught hours, language,
    teaching period, the TAF category that says whether an exam is compulsory
    or elective, and which degree each elective is borrowed from.
    """
    import requests

    esse3 = json.loads((DATA / "esse3.json").read_text())
    want = {a["code"] for a in esse3["remaining"]}
    names = {a["code"]: a["name"] for a in esse3["remaining"]}
    http = requests.Session()
    http.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})

    out: dict[str, dict] = {}
    for year in ("2025", "2024"):
        try:
            payload = http.get(f"{CATALOGUE}/corsi?anno={year}", timeout=180).json()
        except Exception as exc:  # noqa: BLE001
            log("syllabus", year=year, error=repr(exc))
            print(f"  {year}: FAILED ({type(exc).__name__}) - DATA INCOMPLETE")
            continue
        (RAW / "_syllabus").mkdir(parents=True, exist_ok=True)
        (RAW / "_syllabus" / f"corsi-{year}.json").write_text(
            json.dumps(payload, ensure_ascii=False))

        found: list[dict] = []

        def walk(node):
            if isinstance(node, dict):
                if str(node.get("adCod") or "") in want:
                    found.append(node)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        for node in found:
            code = str(node["adCod"])
            if code in out:
                continue
            teachers = [d.get("des") for d in (node.get("docenti") or []) if d.get("des")]
            out[code] = {
                "code": code,
                "name": node.get("des_en") or node.get("des_it"),
                "cfu": node.get("crediti"),
                "taught_hours": node.get("ore"),
                "language": node.get("lingua_des_en"),
                "period": node.get("periodo_didattico_en"),
                "period_start": node.get("data_inizio_periodo_didattico"),
                "period_end": node.get("data_fine_periodo_didattico"),
                "taf": node.get("tafDes_en"),
                "degree_cod": node.get("corso_cod"),
                "cds_cod": node.get("cdsCod"),
                "own_degree": str(node.get("cdsCod")) == config.DEGREE_CODE,
                "af_id": node.get("afId"),
                "teachers": teachers,
                "catalogue_year": year,
                "exam_modality": None,
                "textbooks": None,
                "DATA_INCOMPLETE": ("exam modality and reading list are on the "
                                    "per-course syllabus page, which is not "
                                    "reachable without a browser"),
                "source": f"raw/_syllabus/corsi-{year}.json",
            }
        print(f"  {year}: {len(found)} entries matched, {len(out)} courses resolved")

    missing = sorted(want - set(out))
    (DATA / "syllabus.json").write_text(json.dumps(
        {"courses": out, "not_in_catalogue": missing}, indent=1, ensure_ascii=False))

    # Where the catalogue and Esse3 disagree on CFU, the conflict is the finding.
    esse3_cfu = {a["code"]: a["cfu"] for a in esse3["remaining"]}
    conflicts = [(c, esse3_cfu.get(c), v["cfu"]) for c, v in out.items()
                 if v["cfu"] is not None and esse3_cfu.get(c) != v["cfu"]]
    print(f"\n  {len(out)} courses in the catalogue, {len(missing)} not found")
    for code in missing:
        print(f"    DATA INCOMPLETE {code} {names.get(code,'')[:40]}")
    if conflicts:
        print("  CFU conflicts (Esse3 vs catalogue):")
        for code, a, b in conflicts:
            print(f"    {code} {names.get(code,'')[:34]:<36} Esse3={a} catalogue={b}")
    borrowed = [v for v in out.values() if not v["own_degree"]]
    if borrowed:
        print(f"  {len(borrowed)} taken from another degree (electives): "
              + ", ".join(f"{v['code']} (cds {v['cds_cod']})" for v in borrowed))
    print(f"  wrote {DATA/'syllabus.json'}")
    return 0


# ------------------------------------------------------------ inventory -----
def collect_inventory() -> int:
    """Count what is on disk. Reads names and sizes, never contents."""
    esse3 = json.loads((DATA / "esse3.json").read_text()) if (DATA / "esse3.json").exists() else {}
    remaining = {a["code"]: a for a in esse3.get("remaining", [])}
    rows = []
    for folder in sorted(RAW.glob("[0-9]*")):
        code = folder.name.split("-")[0]
        files = [p for p in folder.rglob("*") if p.is_file()]
        material = [p for p in files if p.suffix.lower() in BINARY_EXT
                    and "_pages" not in p.parts]
        videos, editions = 0, 0
        for meta in folder.glob("*/_meta.json"):
            blob = json.loads(meta.read_text())
            videos += len(blob.get("videos", []))
            editions += 1
        rows.append({
            "code": code,
            "name": remaining.get(code, {}).get("name", folder.name),
            "cfu": remaining.get(code, {}).get("cfu"),
            "editions": editions,
            "material_files": len(material),
            "pdfs": sum(1 for p in material if p.suffix.lower() == ".pdf"),
            "zips": sum(1 for p in material if p.suffix.lower() == ".zip"),
            "html_pages": sum(1 for p in files if p.suffix == ".html"),
            "video_items": videos,
            "bytes": sum(p.stat().st_size for p in files),
            "folder": str(folder.relative_to(ROOT)),
        })
    missing = [c for c in remaining if not any(r["code"] == c for r in rows)]

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "inventory.json").write_text(json.dumps(
        {"courses": rows, "no_material": missing}, indent=1, ensure_ascii=False))

    ANALYSIS.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Inventory", "",
        f"Collected {dt.date.today().isoformat()}. Counts are of files on disk under "
        "`unipv/raw/`; nothing here is an estimate.", "",
        "| Code | Course | CFU | Editions | Files | PDFs | Zips | Pages | Video | Size |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: -r["material_files"]):
        lines.append(
            f"| {row['code']} | {row['name'][:42]} | {row['cfu'] or '?'} | {row['editions']} "
            f"| {row['material_files']} | {row['pdfs']} | {row['zips']} | {row['html_pages']} "
            f"| {row['video_items']} | {row['bytes']/1e6:.1f} MB |")
    total_files = sum(r["material_files"] for r in rows)
    lines += ["", f"**{len(rows)} courses, {total_files} material files, "
                  f"{sum(r['bytes'] for r in rows)/1e6:.0f} MB.**", ""]
    if missing:
        lines += ["## DATA INCOMPLETE", "",
                  "No Kiro material was collected for these — the exam is still to sit:", ""]
        for code in missing:
            lines.append(f"- `{code}` {remaining[code]['name']} "
                         f"({remaining[code].get('cfu','?')} CFU)")
        lines.append("")
    (ANALYSIS / "inventory.md").write_text("\n".join(lines))

    print(f"{'code':<8}{'course':<40}{'files':>6}{'pdfs':>6}{'pages':>7}{'video':>7}{'MB':>8}")
    for row in sorted(rows, key=lambda r: -r["material_files"]):
        print(f"{row['code']:<8}{row['name'][:38]:<40}{row['material_files']:>6}"
              f"{row['pdfs']:>6}{row['html_pages']:>7}{row['video_items']:>7}"
              f"{row['bytes']/1e6:>8.1f}")
    print(f"\n{len(rows)} courses, {total_files} files. "
          f"wrote {DATA/'inventory.json'} and {ANALYSIS/'inventory.md'}")
    if missing:
        print(f"DATA INCOMPLETE for {len(missing)}: {', '.join(missing)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",
                        choices=["esse3", "kiro", "discover", "syllabus", "inventory"])
    parser.add_argument("--no-enrol", action="store_true",
                        help="discover only; do not self-enrol")
    parser.add_argument("--only", help="comma-separated course codes (kiro only)")
    args = parser.parse_args()
    for path in (RAW, DATA, ANALYSIS, LOGS):
        path.mkdir(parents=True, exist_ok=True)
    if args.mode == "esse3":
        return collect_esse3()
    if args.mode == "kiro":
        return collect_kiro(args.only.split(",") if args.only else None)
    if args.mode == "discover":
        return collect_discover(args.only.split(",") if args.only else None,
                                enrol=not args.no_enrol)
    if args.mode == "syllabus":
        return collect_syllabus()
    return collect_inventory()


if __name__ == "__main__":
    raise SystemExit(main())
