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

SIGNATURE = os.environ.get("OUTREACH_SIGNATURE", "")
MAX_WHATSAPP_PER_DAY = int(os.environ.get("MAX_WHATSAPP_PER_DAY", "25"))

# Said in plain Italian, the way a person would describe the problem.
PROBLEM_IT = {
    "no_website": "non ha un sito web",
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
- Nessun markdown, nessun emoji. Solo testo."""


def describe(findings):
    """The findings as one Italian phrase, worst first."""
    return ", ".join(PROBLEM_IT.get(f["code"], f["code"]) for f in findings[:2])


def draft_opener(lead, findings):
    """Write the first message. Falls back to a plain template if the model
    is unavailable, because a queued lead with no draft is worse than a
    slightly blunter sentence."""
    problem = describe(findings)
    if not problem:
        return None

    prompt = f"""Attività: {lead['name']} ({lead.get('category') or 'attività locale'}, {lead.get('city') or 'Milano'})
Problema trovato sul loro sito: {problem}
Dettaglio tecnico: {findings[0].get('detail', '')}

Scrivi il messaggio."""
    try:
        text = ask_volume(prompt, system=DRAFT_SYSTEM, max_tokens=300, temperature=0.4)
        return text.strip()
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
    from .email_reader import _composio_rpc, COMPOSIO_MCP_URL
    import requests

    key = os.environ.get("COMPOSIO_CONSUMER_KEY")
    if not key:
        raise RuntimeError("COMPOSIO_CONSUMER_KEY is not set; cannot send mail")
    if not lead.get("email"):
        raise RuntimeError(f"lead {lead['id']} has no email address")

    headers = {"x-consumer-api-key": key, "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    session = requests.Session()
    response, _ = _composio_rpc(session, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "ai-assistant", "version": "1"}}}, headers)
    if response.headers.get("mcp-session-id"):
        headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
    _composio_rpc(session, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  headers, expect_reply=False)

    call = {"tool_slug": "GMAIL_SEND_EMAIL",
            "arguments": {"recipient_email": lead["email"], "subject": subject,
                          "body": body + (f"\n\n{SIGNATURE}" if SIGNATURE else "")}}
    account = os.environ.get("COMPOSIO_GMAIL_ACCOUNT")
    if account:
        call["account"] = account

    _, reply = _composio_rpc(session, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "COMPOSIO_MULTI_EXECUTE_TOOL",
                   "arguments": {"thought": "send an approved outreach email",
                                 "tools": [call]}}}, headers)
    result = reply.get("result", {})
    text = "".join(c.get("text", "") for c in result.get("content", [])
                   if c.get("type") == "text")
    if result.get("isError"):
        raise RuntimeError(text[:200])
    inner = json.loads(text)["data"]["results"][0]["response"]
    if not inner.get("successful", False):
        raise RuntimeError(str(inner.get("error"))[:200])
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

    if len(parts) == 2:
        parts.append("\nNiente in coda. Aggiungi lead con /add o lancia /scan.")

    summary = " · ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
    parts += ["", "━" * 24, summary]
    return "\n".join(parts)
