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

# Said in plain Italian, the way a person would describe the problem.
PROBLEM_IT = {
    # Sourced from OpenStreetMap, where a missing website tag means nobody
    # mapped one - not that none exists. Claiming otherwise to a practice that
    # has a site ends the conversation on the first line.
    "no_website": "non riesco a trovare un vostro sito web online",
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


def describe(findings, min_severity=2):
    """The findings as one Italian phrase, worst first.

    Trivia is filtered out: an opener that lists a real problem and then pads
    it with something minor reads like a form letter, and the minor checks are
    the ones most likely to be wrong.
    """
    real = [f for f in findings if f["severity"] >= min_severity]
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
    """Subject naming the concrete problem, as in the plan."""
    code = findings[0]["code"] if findings else None
    return {
        "no_website": f"{lead['name']}: non vi trovo online",
        "site_down": f"Il vostro sito non si apre",
        "ssl_expired": "Il vostro sito mostra un avviso di sicurezza",
        "ssl_expiring": "Il certificato del vostro sito sta per scadere",
        "not_mobile": "Il vostro sito non si apre bene da cellulare",
        "slow": "Il vostro sito impiega troppo a caricare",
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

    if buckets["to_call"]:
        parts.append(f"\n📞 DA CHIAMARE OGGI ({len(buckets['to_call'])})")
        for lead in buckets["to_call"][:10]:
            parts.append(format_lead(lead))
            draft = (lead.get("draft") or "").strip().splitlines()
            if draft:
                parts.append(f"   apertura: {draft[0][:110]}")

    if buckets["to_whatsapp"]:
        parts.append(f"\n💬 WHATSAPP DA INVIARE ({len(buckets['to_whatsapp'])})")
        for lead in buckets["to_whatsapp"][:MAX_WHATSAPP_PER_DAY]:
            parts.append(format_lead(lead))
            parts.append(f"   /wa {lead['id']}  per il link già scritto")

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
