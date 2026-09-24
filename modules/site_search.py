"""Automated no-site verification.

A lead scanned from OpenStreetMap that carries only the guessed 'no_website'
finding (missing website tag, not something observed) cannot be written to:
that finding is below SENDABLE on purpose (see modules/scanner.py). This
module turns the guess into something that may be asserted, by actually
searching for the practice and having two independent models look at the
same results:

    model A  decides whether the practice has its OWN site (not a
             directory, not Facebook, not Google Maps) and must cite a URL
    model B  is told to REFUTE "this practice has no website", from a
             different company than model A, on the same results

Only when both conclude there is no own site, and at least
MIN_RELEVANT_RESULTS results actually mention the practice, is the guess
promoted to 'no_site_found' - the one finding severe enough to send. If
either model finds a real site, that goes on the lead instead, so it will be
scanned normally. Anything else - a parse error, a timeout, disagreement,
too few relevant results - leaves the lead unchanged; this only adds
evidence, it never removes it.

Single automated checks have been wrong 20-40% of the time before, so the
decision logic below is a pure function you can unit-test without a network
or a model: decide(lead, results, verdict_a, verdict_b) -> (action, detail).

    python -m modules.site_search_runner [n]

Idempotent per lead: a lead that already carries a 'site_search' event is
skipped, so re-running this costs nothing.
"""

import os
import re
import sys
import json
import datetime

import requests

from . import leads as store
from . import composio_mcp

MIN_RELEVANT_RESULTS = 4

ROUTER_URL = os.environ.get("VOLUME_BASE_URL", "http://127.0.0.1:20128/v1").rstrip("/") + "/chat/completions"
ROUTER_KEY_ENV = "VOLUME_API_KEY"
# Two different companies on purpose: an OpenAI-family model deciding, and a
# model from someone else told to argue the opposite side. Overridable so a
# model that goes down does not need a code change.
MODEL_A = os.environ.get("SITE_SEARCH_MODEL_A", "cx/gpt-5.6-sol")
MODEL_B = os.environ.get("SITE_SEARCH_MODEL_B", "gcli/grok-4.7")

# Directories, map listings and social pages are never "the practice's own
# site" - a model citing one of these as evidence of a website is wrong in
# the way this whole module exists to catch.
DIRECTORY_DOMAINS = {
    "paginegialle.it", "paginebianche.it", "miodottore.it", "prontopro.it",
    "facebook.com", "m.facebook.com", "instagram.com", "linkedin.com",
    "twitter.com", "x.com", "google.com", "maps.google.com", "goo.gl",
    "g.page", "maps.app.goo.gl", "virgilio.it", "yelp.com", "yelp.it",
    "tripadvisor.it", "tripadvisor.com", "cylex.it", "192.it",
    "trovanumeri.it", "subito.it", "kompass.com", "europages.it",
    "hotfrog.it", "aziende.it", "italyaziende.it", "trovaprezzi.it",
    "tuttocitta.it", "paginemediche.it", "pagellepolitiche.it", "impresaitalia.net",
    "guidamedici.it", "dottori.it", "doveecomemicuro.it",
}


def domain_of(url):
    if not url:
        return ""
    host = url.strip().lower().split("//")[-1].split("/")[0]
    return host.removeprefix("www.")


def is_directory(url):
    host = domain_of(url)
    return any(host == d or host.endswith("." + d) for d in DIRECTORY_DOMAINS)


def _name_tokens(lead):
    """Words from the practice name worth matching, longer ones first so
    "srl"/"studio" alone never counts as a match."""
    stop = {"studio", "dott", "dott.ssa", "dr", "di", "e", "del", "della",
            "srl", "snc", "sas", "associato", "associati"}
    words = re.findall(r"[a-zà-ÿ']+", (lead.get("name") or "").lower())
    return [w for w in words if len(w) > 3 and w not in stop]


def _phone_digits(lead):
    digits = "".join(c for c in (lead.get("phone") or "") if c.isdigit())
    return digits[-9:] if len(digits) >= 9 else None


def relevant_results(lead, results):
    """Results that actually say something about this practice, rather than
    a generic hit on the city or the category - what "examined" means for
    the 4-result threshold."""
    tokens = _name_tokens(lead)
    phone = _phone_digits(lead)
    out = []
    for r in results:
        blob = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
        if phone and phone in "".join(c for c in blob if c.isdigit()):
            out.append(r)
            continue
        if tokens and any(t in blob for t in tokens):
            out.append(r)
    return out


def valid_own_site(url, results):
    """`url` only counts as evidence of a real site when it is one of the
    URLs actually returned by the search (a model cannot invent one) and is
    not a directory, map or social page."""
    if not url:
        return None
    url = url.strip()
    result_urls = {(r.get("url") or "").strip() for r in results}
    if url not in result_urls:
        return None
    if is_directory(url):
        return None
    return url


def decide(lead, results, verdict_a, verdict_b):
    """Pure decision logic - no network, no model call.

    verdict_a / verdict_b: {"has_own_site": bool|None, "url": str|None}, as
    parsed from each model's reply.

    Returns (action, detail):
      ("found_site", url)          - a real site was found; set it
      ("no_site_confirmed", None)  - promote the guess to no_site_found
      ("inconclusive", reason)     - leave the lead unchanged
    """
    url_a = valid_own_site(verdict_a.get("url"), results) if verdict_a.get("has_own_site") else None
    url_b = valid_own_site(verdict_b.get("url"), results) if verdict_b.get("has_own_site") else None
    found = url_a or url_b
    if found:
        return "found_site", found

    if verdict_a.get("has_own_site") is False and verdict_b.get("has_own_site") is False:
        n = len(relevant_results(lead, results))
        if n >= MIN_RELEVANT_RESULTS:
            return "no_site_confirmed", None
        return "inconclusive", f"only {n} relevant result(s), need {MIN_RELEVANT_RESULTS}"

    return "inconclusive", "models disagree, or a verdict could not be parsed"


# ── search + model calls (network; not covered by the unit tests) ─────────

def search_queries(lead):
    parts = [p for p in (lead.get("name"), lead.get("city"), lead.get("category")) if p]
    queries = [" ".join(parts), f"{lead.get('name', '')} sito ufficiale"]
    if lead.get("phone"):
        queries.append(lead["phone"])
    return queries[:3]


def _extract_results(data):
    """COMPOSIO_SEARCH_WEB's actual shape (checked against a live call):
    {"answer": "<synthesised text, with [1][2].. markers>",
     "citations": [{"title", "url", "id", "image", ...}, ...]}
    - not a plain list of results under "results"/"organic"/"items". There is
    no per-citation snippet, so the shared answer text stands in for one:
    it is what most often actually names the practice or its phone number,
    which relevant_results() and valid_own_site() key off.
    """
    answer = (data.get("answer") or "")[:600]
    citations = data.get("citations") or []
    # Still accept a plain list shape, in case a future search engine behind
    # the tool returns one instead - cheap to keep, costs nothing when unused.
    items = citations or data.get("results") or data.get("organic") or data.get("items") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        url = (it.get("url") or it.get("link") or it.get("id") or "").strip()
        if not url:
            continue
        out.append({
            "title": it.get("title") or "",
            "url": url,
            "snippet": it.get("snippet") or it.get("description") or answer,
        })
    return out


def collect_results(lead):
    """Composio web search, 2-3 queries, deduplicated by URL. Network only;
    nothing is stored here."""
    collected = []
    for query in search_queries(lead):
        try:
            data = composio_mcp.execute("COMPOSIO_SEARCH_WEB", {"query": query},
                                        thought=f"no-site check for {lead['name']} ({lead.get('city')})")
        except Exception as e:
            print(f"   search failed for {query!r}: {e}")
            continue
        collected.extend(_extract_results(data))

    seen, out = set(), []
    for r in collected:
        if not r["url"] or r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append(r)
    return out


def _router_call(model, prompt, max_tokens=400):
    key = os.environ.get(ROUTER_KEY_ENV, "")
    response = requests.post(
        ROUTER_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "X-9Router-Token-Saver": "off"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens, "temperature": 0, "stream": False},
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _parse_verdict(text):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object in reply: {text[:200]!r}")
    obj = json.loads(text[start:end + 1])
    return {"has_own_site": obj.get("has_own_site"), "url": (obj.get("url") or None)}


def build_prompt(lead, results, refute):
    listing = "\n".join(f"- {r['title']} | {r['url']} | {r['snippet'][:200]}"
                        for r in results[:10]) or "(nessun risultato)"
    task = ('Il tuo compito è provare a CONFUTARE l\'affermazione "questo studio non ha un sito '
            'web proprio", usando solo i risultati sotto.' if refute else
            "Decidi se questo studio professionale ha un proprio sito web (non una directory, "
            "non Facebook/Instagram, non Google Maps, non un elenco di dottori/professionisti).")
    return (f"Studio/attività: {lead.get('name')}\nCittà: {lead.get('city')}\n"
            f"Categoria: {lead.get('category')}\nTelefono: {lead.get('phone') or lead.get('whatsapp') or ''}\n\n"
            f"Risultati di ricerca:\n{listing}\n\n{task}\n\n"
            'Rispondi SOLO con un oggetto JSON: '
            '{"has_own_site": true o false, "url": "<url del sito proprio, o null>", '
            '"reason": "<una frase breve>"}')


def _call_model(model, lead, results, refute, pipeline, step):
    """Call one model through the router, logged to the lab's event log (the
    dashboard's Agenti tab) when that logger is on the path; a plain,
    uninstrumented call otherwise."""
    prompt = build_prompt(lead, results, refute)
    try:
        # ~/portfolio-lab/runlog.py - not part of this repo, not always on
        # sys.path (this module also runs standalone, from cron, from a
        # shell with a different cwd). Its events feed the phone
        # dashboard's Agenti tab, so a call here should show up there.
        lab_dir = os.path.expanduser("~/portfolio-lab")
        if lab_dir not in sys.path and os.path.isdir(lab_dir):
            sys.path.insert(0, lab_dir)
        import runlog
        eid = runlog.start(model, prompt, pipeline=pipeline, step=step)
    except Exception:
        runlog, eid = None, None

    started = datetime.datetime.now()
    try:
        text = _router_call(model, prompt)
        verdict = _parse_verdict(text)
        if runlog:
            runlog.end(eid, "ok", seconds=(datetime.datetime.now() - started).total_seconds(),
                       output_preview=text)
        return verdict
    except Exception as e:
        if runlog:
            runlog.end(eid, "error", seconds=(datetime.datetime.now() - started).total_seconds(),
                       error=str(e))
        raise


def ask_model_a(lead, results):
    return _call_model(MODEL_A, lead, results, refute=False,
                       pipeline="site_search", step=f"lead-{lead['id']}-a")


def ask_model_b(lead, results):
    return _call_model(MODEL_B, lead, results, refute=True,
                       pipeline="site_search", step=f"lead-{lead['id']}-b")


# ── candidates + the per-lead run ──────────────────────────────────────────

EVENT_KIND = "site_search"


def candidates(limit=200):
    """NEW leads with a WhatsApp mobile whose only finding is the guessed
    no_website, not already checked."""
    out = []
    for lead in store.list_leads(state="NEW", limit=store.LEADS_LIST_CAP):
        if not lead.get("whatsapp"):
            continue
        codes = {f["code"] for f in store.findings_of(lead)}
        if codes != {"no_website"}:
            continue
        if store.has_event(lead["id"], EVENT_KIND):
            continue
        out.append(lead)
    return out[:limit]


def check_one(lead):
    """Run the whole pipeline for one lead. Always logs a 'site_search'
    event, even on failure or when inconclusive, so this never re-checks the
    same lead twice. Returns the action taken."""
    today = datetime.date.today().isoformat()
    try:
        results = collect_results(lead)
        verdict_a = ask_model_a(lead, results)
        verdict_b = ask_model_b(lead, results)
        action, detail = decide(lead, results, verdict_a, verdict_b)
    except Exception as e:
        store.log_event(lead["id"], EVENT_KIND, f"error: {e}")
        print(f"   [{lead['id']}] {lead['name']}: error - {e}")
        return "error"

    if action == "found_site":
        store.set_website(lead["id"], detail)
        store.add_note(lead["id"], f"auto-checked {today}: found own site {detail}")
        store.log_event(lead["id"], EVENT_KIND, f"found_site {detail}")
        print(f"   [{lead['id']}] {lead['name']}: found own site {detail}")

    elif action == "no_site_confirmed":
        existing = store.findings_of(lead)
        finding = {"code": "no_site_found",
                   "detail": f"auto-checked {today}: search + 2 models"}
        try:
            from .scanner import SEVERITY
            finding["severity"] = SEVERITY.get("no_site_found", 3)
        except Exception:
            finding["severity"] = 3
        findings = existing + [finding]
        from . import outreach
        draft = outreach.draft_opener(lead, findings)
        store.save_scan(lead["id"], findings, draft)
        urls = ", ".join(r["url"] for r in results[:6] if r.get("url"))
        store.add_note(lead["id"], f"auto-checked {today}: no own site found. Evidence: {urls}")
        store.log_event(lead["id"], EVENT_KIND, "no_site_confirmed")
        print(f"   [{lead['id']}] {lead['name']}: no_site_found confirmed")

    else:
        store.log_event(lead["id"], EVENT_KIND, f"inconclusive: {detail}")
        print(f"   [{lead['id']}] {lead['name']}: inconclusive - {detail}")

    return action


def run(limit=200):
    """Check every eligible lead once. Returns a summary dict."""
    summary = {"checked": 0, "found_site": 0, "no_site_confirmed": 0,
               "inconclusive": 0, "error": 0}
    for lead in candidates(limit):
        action = check_one(lead)
        summary["checked"] += 1
        summary[action] = summary.get(action, 0) + 1
    return summary


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    print(run(n))
