"""Drafting and delivery. Nothing here sends without an explicit instruction.

The cascade is WhatsApp, then email, then a phone call, and every step is a
tap you make in Telegram:

  * WhatsApp  a wa.me link with the message pre-filled. Bulk cold messaging
              gets numbers banned and bans are hard to undo, so the server
              never touches WhatsApp itself.
  * Email     drafted here, sent only when you reply /email <id>.
  * Call      it reaches your digest with the number and an opening line.

Italy's Codice Privacy art. 130 treats unsolicited commercial email and
messaging as consent-based, so "you pressed send" is not a formality.
"""

import os
import json
import urllib.parse

from .llm import ask_volume, VolumeLLMError
from . import leads as leads_store

def signature():
    """Who is writing. Set with /signature in Telegram, or OUTREACH_SIGNATURE.

    Stored in the database so changing it does not mean editing .env and
    restarting the service mid-conversation.
    """
    return leads_store.get_setting("signature", os.environ.get("OUTREACH_SIGNATURE", "")).strip()

# Every email says who is writing, how they found the business, and how to
# stop hearing from you. That is the user's own rule for outreach, and it is
# also what makes a first message defensible rather than spam.
OPT_OUT_IT = ("Le scrivo perché ho trovato i vostri contatti pubblicati online. "
              "Se preferisce non ricevere altri messaggi, risponda a questa email "
              "e non la contatterò più.")


def email_footer():
    return "\n\n--\n" + signature() + "\n" + OPT_OUT_IT
MAX_WHATSAPP_PER_DAY = int(os.environ.get("MAX_WHATSAPP_PER_DAY", "25"))
# Cold email from a personal Gmail: a burst of them is what gets the account
# flagged, and it is the address every reply comes back to.
MAX_EMAIL_PER_DAY = int(os.environ.get("MAX_EMAIL_PER_DAY", "20"))

# Said in plain Italian, the way a person would describe the problem.
PROBLEM_IT = {
    # Sourced from OpenStreetMap, where a missing website tag means nobody
    # mapped one - not that none exists. Claiming otherwise to a practice that
    # has a site ends the conversation on the first line.
    "no_website": "non risulta un sito web nelle mappe online",
    "no_site_found": "cercando online non si trova un sito dello studio",
    "mobile_overflow": "sul telefono una parte della pagina esce dallo schermo",
    "listed_page_gone": "la pagina collegata alla scheda sulle mappe non esiste più",
    "domain_gone": "il dominio del sito non risulta più attivo",
    "ssl_wrong_host": "il certificato di sicurezza è di un altro indirizzo, il browser avvisa",
    "site_down": "il sito non si apre",
    "ssl_expired": "il certificato di sicurezza è scaduto, il browser mostra un avviso",
    "ssl_expiring": "il certificato di sicurezza sta per scadere",
    "not_mobile": "il sito non si vede bene da cellulare",
    "slow": "il sito è molto lento a caricare",
    "no_english": "il sito è solo in italiano",
}

DRAFT_SYSTEM = """Sei un professionista italiano che scrive un primo messaggio
a un'attività locale. Scrivi in italiano, dai del Lei, massimo 4 frasi.
Regole:
- Nomina SUBITO il problema concreto trovato, senza giri di parole.
- Niente complimenti finti, niente "spero che questa email La trovi bene".
- Niente promesse di risultati, niente percentuali inventate.
- Chiudi con una domanda semplice, non con un invito a comprare.
- MAI termini tecnici o parole inglesi: niente "viewport", "meta tag",
  "certificate", "SSL", "responsive". Scrivi come parleresti al telefono.
- Descrivi solo il problema indicato, non aggiungerne altri.
- Nessun markdown, nessun emoji. Solo testo."""


def severity_now(finding):
    """The finding's severity as the scanner rates it TODAY.

    The stored number is whatever it was worth on the night of the scan.
    Demoting a check (no_website went from 3 to 1 on 2026-09-23, after an
    audit found live sites behind that guess) has to take effect without
    rescanning 244 leads, so every send decision looks the code up again.
    """
    from .scanner import SEVERITY
    return SEVERITY.get(finding["code"], finding.get("severity", 0))


def describe(findings, min_severity=2):
    """The findings as one Italian phrase, worst first.

    Trivia is filtered out: an opener that lists a real problem and then pads
    it with something minor reads like a form letter, and the minor checks are
    the ones most likely to be wrong.
    """
    real = [f for f in findings if severity_now(f) >= min_severity]
    return ", ".join(PROBLEM_IT.get(f["code"], f["code"]) for f in real[:2])


TEMPLATE_MARKER = "Me ne occupo per attività come la vostra"


def is_template_draft(draft):
    """True when the model refused and the plain template was used instead.

    Worth knowing: a template draft is serviceable but generic, and generic is
    what makes cold outreach look like cold outreach.
    """
    return bool(draft) and TEMPLATE_MARKER in draft


def draft_opener(lead, findings):
    """Write the first message. Falls back to a plain template if the model
    is unavailable, because a queued lead with no draft is worse than a
    slightly blunter sentence."""
    problem = describe(findings)
    if not problem:
        return None

    # The technical detail stays out of the prompt on purpose: the model
    # quoted it verbatim ("certificate has expired") into a message meant for
    # a dentist. PROBLEM_IT already says it in plain Italian.
    # Name the address when the problem is about a specific site. Most dead
    # sites in the list fail at DNS - an expired domain - and the practice may
    # have moved. "Il sito pentadent.it non si apre" is checkable and true;
    # "il vostro sito non si apre" is a claim they can refute with a new URL.
    host = ""
    if lead.get("website") and findings[0]["code"] in ("site_down", "ssl_expired",
                                                        "ssl_expiring", "not_mobile", "slow"):
        import urllib.parse
        url = lead["website"] if "://" in lead["website"] else "https://" + lead["website"]
        host = (urllib.parse.urlparse(url).hostname or "").removeprefix("www.")
    prompt = f"""Attività: {lead['name']} ({lead.get('category') or 'attività locale'}, {lead.get('city') or 'Milano'})
Problema trovato: {problem}""" + (f"\nIndirizzo del sito: {host} (citalo per nome)" if host else "") + """

Scrivi il messaggio."""
    try:
        # Generous budget: reasoning models spend part of it thinking, and a
        # draft cut off mid-sentence is worse than a plain template.
        text = ask_volume(prompt, system=DRAFT_SYSTEM, max_tokens=900, temperature=0.4).strip()
        if text and text.rstrip()[-1] not in ".?!\"":
            print("   draft looks truncated, using the template instead")
            raise VolumeLLMError("truncated draft")
        return text
    except VolumeLLMError as e:
        print(f"   draft fell back to template: {e}")
        return (f"Buongiorno, ho visto che {problem} per {lead['name']}. "
                f"Me ne occupo per attività come la vostra qui a {lead.get('city') or 'Milano'}. "
                f"Volete che vi mandi due righe su come sistemarlo?")


def whatsapp_link(lead, text):
    """wa.me link with the message pre-filled - you still press send."""
    number = (lead.get("whatsapp") or "").lstrip("+").replace(" ", "")
    if not number:
        return None
    return f"https://wa.me/{number}?text={urllib.parse.quote(text)}"


def whatsapp_app_link(lead, text):
    """Same, as the app's own scheme. From an iPhone home-screen web app a
    wa.me link opens a web page with a "continue to chat" button first; this
    goes straight to the chat, the way tel: goes straight to the dialler."""
    number = (lead.get("whatsapp") or "").lstrip("+").replace(" ", "")
    if not number:
        return None
    return f"whatsapp://send?phone={number}&text={urllib.parse.quote(text)}"


# The WhatsApp opener is assembled here, not by the model. It goes out under
# Momo's own number, and the parts that make a cold message defensible - who
# is writing, where the number came from, how to make it stop - are the parts
# the model left out: none of the WhatsApp drafts written before 2026-09-22
# said who was writing.

# One sentence per problem, naming the site so it can be checked.
WA_PROBLEM = {
    # Each sentence says exactly what was done and what was seen. The audit
    # found the old ones claiming a phone we never used, an expiry that had
    # not happened, and a site that was down only at www.
    "site_down": "Ho provato ad aprire {site}, con e senza www, e non risponde.",
    "domain_gone": "Ho provato ad aprire {site} e il dominio non risulta più registrato o attivo.",
    "ssl_wrong_host": "Aprendo {site} il browser avvisa che il sito non è sicuro: il certificato di sicurezza è intestato a un altro indirizzo.",
    "ssl_expired": "Aprendo {site}, il browser avvisa che il sito non è sicuro: il certificato di sicurezza è scaduto.",
    "ssl_expiring": "Il certificato di sicurezza di {site} sta per scadere, e quando scade il browser avvisa chi lo apre che il sito non è sicuro.",
    "not_mobile": "Ho aperto {site} su uno schermo da telefono e la pagina non si adatta: si legge solo spostandola di lato.",
    "no_website": ("Non riesco a trovare un vostro sito web: se non ce l'avete, ne preparo uno "
                   "semplice e chiaro, che si legge bene anche dal telefono."),
    # "il vostro studio", not the map name: pasted in, "Dott. Lanza Matteo
    # Luciano consulente tributario" reads like a mail merge, and a bare
    # person's name like searching for the person. "o social" because some
    # have only a Facebook page.
    "no_site_found": ("Ho cercato {practice} su internet e non trovo un vostro sito: ci sono solo "
                      "le schede su mappe, portali o social. Se non ne avete uno, ne preparo uno "
                      "semplice e chiaro, che si legge bene anche dal telefono."),
}

# What else Momo builds, offered once and softly. "Se non li usate già"
# because nothing checked tells us they lack it - it is a guess from the kind
# of practice, and a guess stated as a fact is how an opener loses the reader.
APPOINTMENT_TRADES = ("dentist", "fisioterap", "veterinar", "psicolog", "medic", "odontoiatr")
DOCUMENT_TRADES = ("commercialist", "avvocat", "notai", "notaio", "architett", "consulent")


def extra_offer(lead):
    """The one other thing worth mentioning to this kind of practice, or None."""
    category = (lead.get("category") or "").lower()
    if any(t in category for t in APPOINTMENT_TRADES):
        who = "i clienti" if "veterinar" in category else "i pazienti"
        return f"Se non li usate già, posso preparare anche i promemoria degli appuntamenti su WhatsApp per {who}."
    if any(t in category for t in DOCUMENT_TRADES):
        return "Se può servire, posso preparare anche un modo semplice per ricevere i documenti dai clienti, tutti in un unico posto."
    return None


def _site_name(lead):
    if not lead.get("website"):
        return "il vostro sito"
    url = lead["website"] if "://" in lead["website"] else "https://" + lead["website"]
    return (urllib.parse.urlparse(url).hostname or "").removeprefix("www.") or "il vostro sito"


def _practice(lead):
    text = f"{lead.get('category') or ''} {lead['name']}".lower()
    return "il vostro ambulatorio" if "veterinar" in text or "ambulatori" in text else "il vostro studio"


def _where_found(lead):
    if (lead.get("source") or "").startswith("osm:"):
        return "Ho trovato il vostro numero su OpenStreetMap, la mappa online."
    return "Ho trovato il vostro numero tra i contatti pubblici dello studio."


def _opener(lead, findings, hour=None):
    """The parts every first message shares - greeting, who is writing, the
    one problem with its question, the optional extra - or None when nothing
    found is worth writing about.

    One problem only. describe() can name two, but a stranger's first message
    listing what is wrong with your practice reads like an audit; the extra
    line offers something instead of finding another fault.
    """
    real = [f for f in findings if severity_now(f) >= 2 and f["code"] in WA_PROBLEM]
    if not real:
        return None
    code = real[0]["code"]
    if hour is None:
        import datetime
        hour = datetime.datetime.now().hour
    greeting = "Buonasera" if hour >= 17 else "Buongiorno"
    # Two phrasings, picked by id: the same text sent to many numbers is what
    # WhatsApp's spam detection looks for.
    who = ("sono Momo: faccio siti web e automazioni per studi professionali, tra Pavia e Milano.",
           "mi chiamo Momo e mi occupo di siti web e automazioni per studi professionali, tra Pavia e Milano.")[lead["id"] % 2]
    problem = WA_PROBLEM[code].format(site=_site_name(lead), practice=_practice(lead))
    if code == "no_site_found":
        question = "Le interessa vedere un sito che ho fatto?"
    elif code == "domain_gone":
        question = "Avete cambiato indirizzo, o il sito non c'è più?"
    elif code == "no_website":
        question = "Le interessa vedere un sito che ho fatto?"
    else:
        question = ("Vuole che le spieghi in due righe da cosa dipende e come si sistema?",
                    "Le interessa che le scriva in due righe da cosa dipende e come lo sistemerei?")[lead["id"] % 2]
    return greeting, who, f"{problem} {question}", extra_offer(lead)


def whatsapp_message(lead, findings, hour=None):
    """The first WhatsApp message: who is writing, the one problem found, a
    question, at most one other offer, and where the number came from."""
    parts = _opener(lead, findings, hour)
    if not parts:
        return None
    greeting, who, ask, extra = parts
    # The question follows the problem it is about; the extra offer gets its
    # own line after it, so the one thing being asked stays obvious.
    lines = [f"{greeting}, {who}", ask, extra,
             f"{_where_found(lead)} Se preferisce non ricevere altri messaggi, me lo scriva e non la ricontatto."]
    return "\n\n".join(p for p in lines if p)


def email_message(lead, findings, hour=None):
    """The same opener as an email body. Where the address came from and how
    to opt out are not repeated here: send_email appends email_footer(), with
    the signature and OPT_OUT_IT, to every message."""
    parts = _opener(lead, findings, hour)
    if not parts:
        return None
    greeting, who, ask, extra = parts
    lines = [f"{greeting},", who[0].upper() + who[1:], ask, extra, "Un saluto,\nMomo"]
    return "\n\n".join(p for p in lines if p)


def send_email(lead, subject, body):
    """Send through Composio's Gmail connection. Called only on approval."""
    from . import composio_mcp

    if not lead.get("email"):
        raise RuntimeError(f"lead {lead['id']} has no email address")
    # Fail closed: an unsigned cold email is what the outreach rules here
    # exist to prevent, so refuse rather than send one anonymously.
    if not signature():
        raise RuntimeError("nessuna firma impostata: usa /signature Nome, cosa fai, contatto")

    composio_mcp.execute(
        "GMAIL_SEND_EMAIL",
        {"recipient_email": lead["email"], "subject": subject,
         "body": body + email_footer()},
        thought="send an outreach email the user approved in telegram",
        account=os.environ.get("COMPOSIO_GMAIL_ACCOUNT") or None)
    return True


def subject_for(lead, findings):
    """Subject naming the problem and the exact address it was seen at.

    "Il vostro sito non si apre" is a claim about a site they can point at;
    "studiorossi.it non risponde" is a fact they can check in ten seconds.
    """
    code = findings[0]["code"] if findings else None
    site = _site_name(lead)
    return {
        "no_website": f"{lead['name']}: non vi trovo online",
        "no_site_found": f"{lead['name']}: non trovo un vostro sito",
        "domain_gone": f"{site}: il dominio non risulta più attivo",
        "ssl_wrong_host": f"{site}: il browser avvisa che il sito non è sicuro",
        "site_down": f"{site} non risponde",
        "ssl_expired": f"{site}: il certificato di sicurezza è scaduto",
        "ssl_expiring": f"{site}: il certificato di sicurezza sta per scadere",
        "not_mobile": f"{site} non si adatta allo schermo del telefono",
    }.get(code, f"Due righe sul sito di {lead['name']}")


def format_lead(lead, index=None):
    findings = leads_store.findings_of(lead)
    head = f"[{lead['id']}] {lead['name']}"
    if lead.get("city"):
        head += f" - {lead['city']}"
    lines = [head]
    if findings:
        lines.append(f"   problema: {describe(findings)}")
    if lead.get("phone"):
        lines.append(f"   tel: {lead['phone']}")
    return "\n".join(lines)


def format_digest(buckets, counts):
    """The 08:00 message: what is waiting, in the order it should be done."""
    parts = ["☀️ Lead del giorno", "━" * 24]

    # Messages first: Momo would rather write than ring.
    if buckets["to_whatsapp"]:
        parts.append(f"\n💬 WHATSAPP DA INVIARE ({len(buckets['to_whatsapp'])})")
        for lead in buckets["to_whatsapp"][:MAX_WHATSAPP_PER_DAY]:
            parts.append(format_lead(lead))
            parts.append(f"   /wa {lead['id']}  per il link già scritto")

    if buckets["to_call"]:
        parts.append(f"\n📞 DA CHIAMARE OGGI ({len(buckets['to_call'])})")
        for lead in buckets["to_call"][:10]:
            parts.append(format_lead(lead))
            draft = (lead.get("draft") or "").strip().splitlines()
            if draft:
                parts.append(f"   apertura: {draft[0][:110]}")

    if buckets["to_email"]:
        parts.append(f"\n✉️ EMAIL DA APPROVARE ({len(buckets['to_email'])})")
        for lead in buckets["to_email"][:10]:
            parts.append(format_lead(lead))
            parts.append(f"   /draft {lead['id']}  per leggerla, /email {lead['id']} per inviarla")

    if buckets["to_follow_up"]:
        parts.append(f"\n🔁 DA RICONTATTARE ({len(buckets['to_follow_up'])})")
        for lead in buckets["to_follow_up"][:10]:
            parts.append(format_lead(lead))

    if buckets.get("no_angle"):
        parts.append(f"\n⚪ SENZA PROBLEMI TROVATI ({len(buckets['no_angle'])})")
        parts.append("   Il sito funziona: serve un altro motivo per scrivere, "
                     "oppure /dead per toglierli di mezzo.")

    if len(parts) == 2:
        parts.append("\nNiente in coda. Aggiungi lead con /add o lancia /scan.")

    summary = " · ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
    parts += ["", "━" * 24, summary]
    return "\n".join(parts)
