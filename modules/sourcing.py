"""Find businesses to contact, from OpenStreetMap.

Overpass is free, needs no key and no billing account, and its terms allow
this. Coverage of Italian studi professionali is decent but uneven: many
entries carry a phone, fewer carry an email, and some carry neither - those
are dropped, because a lead you cannot contact is not a lead.

    from modules import sourcing
    sourcing.import_niche("dentisti", "Milano", limit=200)

Etiquette matters here: it is a volunteer-run endpoint. One query per run, a
real User-Agent, and a timeout.
"""

import os
import time

import requests

from . import leads as store

OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
USER_AGENT = os.environ.get(
    "OVERPASS_USER_AGENT",
    "ai-assistant/1.0 (personal lead research; contact via telegram bot)")
TIMEOUT = int(os.environ.get("OVERPASS_TIMEOUT", "90"))

# What each niche looks like in OSM tags. Several tags per niche because
# mappers are inconsistent: a dentist may be amenity=dentist or
# healthcare=dentist, and studios often carry office=* instead.
NICHES = {
    "dentisti": [("amenity", "dentist"), ("healthcare", "dentist")],
    "commercialisti": [("office", "accountant"), ("office", "tax_advisor")],
    "avvocati": [("office", "lawyer")],
    "architetti": [("office", "architect")],
    "fisioterapisti": [("healthcare", "physiotherapist")],
    "veterinari": [("amenity", "veterinary")],
    "notai": [("office", "notary")],
    "psicologi": [("healthcare", "psychotherapist"), ("office", "psychologist")],
}


def build_query(niche, city, limit):
    """Overpass QL for one niche inside one comune."""
    tags = NICHES[niche]
    clauses = []
    for key, value in tags:
        for element in ("node", "way"):
            clauses.append(f'  {element}["{key}"="{value}"](area.searchArea);')
    return (
        f"[out:json][timeout:{TIMEOUT}];\n"
        f'area["name"="{city}"]["boundary"="administrative"]->.searchArea;\n'
        "(\n" + "\n".join(clauses) + "\n);\n"
        f"out center tags {limit};"
    )


def _tag(tags, *names):
    for name in names:
        value = tags.get(name)
        if value:
            return value.strip()
    return None


def search(niche, city="Milano", limit=200):
    """Return raw candidates. Network only; nothing is stored here."""
    if niche not in NICHES:
        raise ValueError(f"niche sconosciuta: {niche}. "
                         f"Disponibili: {', '.join(sorted(NICHES))}")

    query = build_query(niche, city, limit)
    # Overpass runs on donated hardware and hands out slots: 429 means wait,
    # not fail. Sourcing several niches in one go hits this every time.
    for attempt in range(4):
        response = requests.post(OVERPASS_URL, data={"data": query},
                                 headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT + 30)
        if response.status_code not in (429, 504):
            break
        wait = 30 * (attempt + 1)
        print(f"   Overpass busy ({response.status_code}), waiting {wait}s")
        time.sleep(wait)
    else:
        raise RuntimeError("Overpass occupato: riprova fra qualche minuto")
    response.raise_for_status()

    candidates = []
    for element in response.json().get("elements", []):
        tags = element.get("tags", {})
        name = _tag(tags, "name", "operator")
        if not name:
            continue
        # OSM packs several numbers into one tag with ";". Unsplit, the digest
        # showed "+39 02 2892827;" and a landline plus a mobile collapsed into
        # one digit string that matched neither.
        raw_phones = ";".join(filter(None, (tags.get(k) for k in
                              ("phone", "contact:phone", "contact:mobile", "mobile"))))
        phones = [p.strip() for p in raw_phones.split(";") if p.strip()]
        candidates.append({
            "name": name,
            "phone": phones[0] if phones else None,
            "all_phones": phones,
            "email": _tag(tags, "email", "contact:email"),
            "website": _tag(tags, "website", "contact:website", "url"),
            "street": _tag(tags, "addr:street"),
            "osm_id": f"{element.get('type')}/{element.get('id')}",
        })
    return candidates


def import_niche(niche, city="Milano", limit=200):
    """Search, filter to the contactable, and store. Returns a summary."""
    from .commands import mobile_number

    candidates = search(niche, city, limit)
    added = duplicate = unreachable = 0

    for candidate in candidates:
        # No phone and no email means nothing to do with it: the website
        # alone gives you a problem to point at but no one to tell.
        if not candidate["phone"] and not candidate["email"]:
            unreachable += 1
            continue
        # Prefer a mobile for WhatsApp if any of the listed numbers is one.
        whatsapp = next((m for m in map(mobile_number, candidate["all_phones"]) if m), None)
        lead_id = store.add_lead(
            candidate["name"], category=niche, city=city,
            website=candidate["website"], email=candidate["email"],
            phone=candidate["phone"], whatsapp=whatsapp,
            source=f"osm:{candidate['osm_id']}")
        if lead_id:
            added += 1
        else:
            duplicate += 1

    return {"found": len(candidates), "added": added, "duplicates": duplicate,
            "unreachable": unreachable}


def summarise(result, niche, city):
    lines = [f"📍 {niche} a {city}",
             f"   trovati: {result['found']}",
             f"   aggiunti: {result['added']}"]
    if result["duplicates"]:
        lines.append(f"   già presenti: {result['duplicates']}")
    if result["unreachable"]:
        lines.append(f"   scartati (nessun contatto): {result['unreachable']}")
    if result["added"]:
        lines.append(f"\n/scan {min(result['added'], 50)} per analizzarli")
    return "\n".join(lines)
