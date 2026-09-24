"""Slash commands for working leads from Telegram.

Parsed before the LLM intent router ever sees the message: "/dead 12" must
mean exactly that, every time, with no model in the loop.

    /briefing             read the inbox and summarise it now
    /kiro                 check the course portal (dormant without credentials)
    /chiama               call mode: one practice at a time, outcome in a tap
    /sito                 switchers.events visitors and Google search
    /app                  six-digit code to sign in to the phone app
    /status               services, memory, models, leads, backups
    /logs [n]             the last n lines of the service log
    /restart [servizio]   restart the assistant, or 9router
    /leads [stato]        what is in the pipeline
    /lead <id>            everything known about one
    /scan [n]             scan unscanned leads and draft openers
    /digest               the 08:00 summary, now
    /shot <id>            the screenshot of what is wrong
    /wa <id>              one-tap WhatsApp link, message pre-filled
    /draft <id>           read the email before it goes
    /email <id>           send that email (this is the approval)
    /sent <id>            you sent the WhatsApp yourself
    /contacted <id> [..]  you spoke to them
    /interested <id>      worth chasing
    /dead <id>            stop spending attention
    /note <id> <text>     remember something
    /signature <testo>    who your emails say they are from
    /add <name> | <city> | <website> | <phone> | <email>
    /import               same format, one lead per line
    /source <niche> <città> [n]   find businesses on OpenStreetMap
"""

import os
import threading

from . import leads as store
from . import outreach
from . import scanner
from .escalate import escalate

HELP = __doc__.split("\n\n", 2)[2]

# What each command does, in the words someone might use for it. This is the
# list the natural-language router picks from, so it is the single place to
# describe a capability.
CATALOGUE = [
    ("/chiama", "inizia a chiamare i lead: uno alla volta, esito con un tocco"),
    ("/sito", "quante persone hanno visitato switchers.events e come va su Google"),
    ("/app", "codice per accedere all'app sul telefono, dashboard"),
    ("/status", "come sta il server, memoria, modelli, quanti lead, backup"),
    ("/logs [n]", "le ultime righe di log del servizio"),
    ("/restart [unit]", "riavvia l'assistente o il router"),
    ("/leads [stato]", "elenco dei lead, eventualmente filtrato per stato"),
    ("/lead <id>", "tutto su un lead: problemi, bozza, note, stato"),
    ("/digest", "riepilogo dei LEAD di lavoro: chi chiamare oggi, quali "
                "messaggi inviare. NON riguarda la posta in arrivo"),
    ("/scan [n]", "analizza i lead non ancora analizzati e scrive le bozze"),
    ("/wa <id>", "link WhatsApp con il messaggio già scritto"),
    ("/shot <id>", "screenshot del problema trovato sul sito"),
    ("/draft <id>", "leggi l'email prima di inviarla"),
    ("/email <id>", "INVIA l'email a quel lead"),
    ("/sent <id>", "segna che hai inviato tu il WhatsApp"),
    ("/contacted <id> [nota]", "hai parlato con loro"),
    ("/interested <id>", "sono interessati"),
    ("/dead <id>", "lead da abbandonare"),
    ("/note <id> <testo>", "annota qualcosa su un lead"),
    ("/add Nome | Città | sito | tel | email", "aggiunge un lead"),
    ("/import <righe>", "aggiunge molti lead, uno per riga"),
    ("/source <niche> <città> [n]", "cerca nuove attività su OpenStreetMap e le "
                                    "aggiunge: dentisti, commercialisti, avvocati, "
                                    "architetti, fisioterapisti, veterinari, notai"),
    ("/signature <testo>", "con che firma partono le email"),
    ("/briefing", "leggi la POSTA IN ARRIVO (Gmail) e riassumi le email "
                  "ricevute: novità nella mail, cosa è arrivato oggi"),
    ("/kiro", "novità sui corsi universitari (spento senza credenziali)"),
]

# Commands the router may run on its own: they only read. Anything that
# sends, changes state, spends quota or restarts a service is handed back for
# the human to tap, because a misread sentence must not email a stranger.
SAFE = {"status", "stato", "logs", "leads", "lead", "digest", "draft", "wa",
        "shot", "help", "aiuto", "start", "chiama", "call", "sito", "switchers",
        "app", "dashboard"}


def mobile_number(phone):
    """Return an Italian mobile in wa.me form, or None.

    Only mobiles have WhatsApp. Italian mobile numbers start with 3 after the
    country code; landlines (02 for Milan, 0382 for Pavia) do not, and a
    wa.me link to one just fails after you have already tapped it.
    """
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("39"):
        national = digits[2:]
    elif digits.startswith("3"):
        national = digits          # local format, already a mobile
    else:
        return None                # landline or unknown country
    if not national.startswith("3") or not 9 <= len(national) <= 11:
        return None
    return "39" + national


def _lead_or_error(arg):
    if not arg or not arg.isdigit():
        return None, "Serve un id: per esempio /lead 3"
    lead = store.get(int(arg))
    if not lead:
        return None, f"Nessun lead con id {arg}"
    return lead, None


def handle(text, send):
    """Run one command. `send` delivers a reply; returns True if handled."""
    parts = text.strip().split(maxsplit=1)
    command = parts[0].lower().lstrip("/")
    rest = parts[1].strip() if len(parts) > 1 else ""
    args = rest.split(maxsplit=1)
    first = args[0] if args else ""

    if command in ("help", "aiuto", "start"):
        send("Comandi:\n" + HELP)

    elif command in ("app", "dashboard") and first in ("logout", "esci", "revoca"):
        # A lost phone could otherwise send from the app for 90 days, and the
        # only way to stop it was editing the database.
        store.set_setting("webapp_sessions", "[]")
        send("🔒 Fatto: l'app è stata scollegata da tutti i telefoni. "
             "Scrivi /app per rientrare.")

    elif command in ("app", "dashboard"):
        # The code goes only to this chat, which the listener has already
        # verified is yours. Single use, ten minutes, five tries.
        from . import webapp
        code = webapp.new_pairing_code()
        url = os.environ.get("WEBAPP_URL", "https://app.momosassistant.it")
        send(f"📱 Codice per l'app:\n\n{code}\n\nApri {url} e inseriscilo. "
             f"Vale {webapp.CODE_MINUTES} minuti, una volta sola.")

    elif command in ("chiama", "call"):
        from . import callmode
        callmode.start(send)

    elif command in ("sito", "switchers"):
        from . import site
        send("⏳ Controllo visite e Google...")
        threading.Thread(target=lambda: send(site.report()), daemon=True).start()

    elif command in ("status", "stato"):
        from . import health
        send(health.summary())

    elif command == "logs":
        lines = first if first.isdigit() else "25"
        import subprocess
        out = subprocess.run(["journalctl", "-u", "assistant", "-n", lines,
                              "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=15).stdout
        # Lines written before a redaction fix can still hold the bot token;
        # this sends them into a chat, so strip it here as well.
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if token:
            out = out.replace(token, "<token>")
        if not out.strip():
            send("Log non leggibili: manca il gruppo systemd-journal?")
        else:
            send("```\n" + out[-3500:] + "\n```")

    elif command == "restart":
        import subprocess
        unit = first if first in ("assistant", "9router", "webapp") else "assistant"
        send(f"♻️ Riavvio {unit}...")
        # Authorised by a polkit rule, not sudo: NoNewPrivileges=true in the
        # unit stops sudo from ever gaining root, and that flag should stay.
        result = subprocess.run(["systemctl", "restart", unit],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            # Restarting itself is the normal case, and systemd kills this
            # process mid-reply; an error here means the polkit rule is missing.
            send(f"❌ {result.stderr.strip()[:200] or 'permesso negato'}")

    elif command == "leads":
        state = first.upper() or None
        rows = store.list_leads(state=state, limit=30)
        if not rows:
            send("Nessun lead." if not state else f"Nessun lead in stato {state}.")
        else:
            send("\n".join(outreach.format_lead(r) for r in rows)
                 + f"\n\n{' · '.join(f'{k}:{v}' for k, v in sorted(store.counts().items()))}")

    elif command == "lead":
        lead, error = _lead_or_error(first)
        if error:
            send(error)
        else:
            findings = store.findings_of(lead)
            lines = [outreach.format_lead(lead), f"stato: {lead['state']}"]
            if lead.get("website"):
                lines.append(f"sito: {lead['website']}")
            if lead.get("email"):
                lines.append(f"email: {lead['email']}")
            if findings:
                lines.append("problemi: " + ", ".join(f["code"] for f in findings))
            script = outreach.call_script(lead, findings)
            if script:
                lines.append("\ncosa dire:\n" + script)
            if lead.get("notes"):
                lines.append("\nnote:\n" + lead["notes"])
            send("\n".join(lines))

    elif command == "scan":
        limit = int(first) if first.isdigit() else 10
        send(f"⏳ Scansione di {limit} lead avviata...")
        # A scan starts Chrome and can run for minutes. On the listener thread
        # that freezes the bot and Telegram updates pile up behind it.
        threading.Thread(target=lambda: send(scan_pending(limit)), daemon=True).start()

    elif command == "digest":
        send(outreach.format_digest(store.due_leads(), store.counts()))

    elif command == "wa":
        lead, error = _lead_or_error(first)
        if error:
            send(error)
        elif not lead.get("whatsapp"):
            send(f"{lead['name']} non ha un numero WhatsApp.")
        else:
            message = outreach.whatsapp_message(lead, store.findings_of(lead))
            if not message:
                send(f"Nessuna bozza per {lead['name']}: la scansione non ha trovato "
                     f"problemi da citare. /scan per riprovare, oppure scriva a mano.")
                return True
            link = outreach.whatsapp_link(lead, message)
            extra = ""
            if os.path.exists(os.path.join(scanner.SHOTS_DIR, f"lead-{lead['id']}.png")):
                extra = f"\n/shot {lead['id']} per lo screenshot da allegare"
            send(f"{lead['name']}\n\n{message}\n\n👉 {link}\n\n"
                 f"Dopo l'invio: /sent {lead['id']}{extra}")

    elif command == "shot":
        lead, error = _lead_or_error(first)
        if error:
            send(error)
        else:
            path = os.path.join(scanner.SHOTS_DIR, f"lead-{lead['id']}.png")
            if not os.path.exists(path):
                send(f"Nessuno screenshot per {lead['name']}. "
                     f"Lo scatto si crea quando la scansione trova un problema di layout.")
            else:
                from . import telegram_bot
                telegram_bot.send_telegram_photo(
                    path, f"{lead['name']}: {outreach.describe(store.findings_of(lead))}")

    elif command == "draft":
        lead, error = _lead_or_error(first)
        if error:
            send(error)
        else:
            # Exactly what /email and the app would send, footer included.
            findings = store.findings_of(lead)
            body = outreach.email_message(lead, findings)
            if not body:
                send(f"Per {lead['name']} non c'è niente di verificato da scrivere.")
            else:
                send(f"A: {lead.get('email') or '(nessuna email)'}\n"
                     f"Oggetto: {outreach.subject_for(lead, findings)}\n\n{body}"
                     f"{outreach.email_footer()}\n\n"
                     f"Per inviare: /email {lead['id']}")

    elif command == "email":
        lead, error = _lead_or_error(first)
        if error:
            send(error)
        elif not lead.get("email"):
            send(f"{lead['name']} non ha un'email.")
        else:
            # The app's sender, so both doors have the same locks: the lead
            # must be in the email queue, not emailed already, under the daily
            # cap, and an unclear failure is never answered with "retry".
            # This used to send the stored model draft with none of those.
            from .webapp import send_lead_email
            findings = store.findings_of(lead)
            body = outreach.email_message(lead, findings)
            if not body:
                send(f"Per {lead['name']} non c'è niente di verificato da scrivere.")
                return True
            status, payload = send_lead_email(lead["id"], outreach.subject_for(lead, findings), body)
            if status == 200:
                send(f"✅ Inviata a {lead['email']}. Se non rispondono, fra "
                     f"{store.EMAIL_WAIT_DAYS} giorni finisce fra le chiamate.")
            else:
                send(f"❌ {payload.get('error', 'invio non riuscito')}")

    elif command == "sent":
        lead, error = _lead_or_error(first)
        if error:
            send(error)
        else:
            store.set_state(lead["id"], "WHATSAPP_SENT", note="sent by hand")
            send(f"Segnato. Se non rispondono, fra {store.WHATSAPP_WAIT_DAYS} giorni passa all'email.")

    elif command in ("contacted", "interested", "dead"):
        lead, error = _lead_or_error(first)
        if error:
            send(error)
        else:
            state = {"contacted": "CONTACTED", "interested": "INTERESTED", "dead": "DEAD"}[command]
            note = args[1] if len(args) > 1 else None
            store.set_state(lead["id"], state, note=note)
            if note:
                store.add_note(lead["id"], note)
            send(f"[{lead['id']}] {lead['name']} → {state}" + (f"\n{note}" if note else ""))

    elif command == "note":
        lead, error = _lead_or_error(first)
        if error or len(args) < 2:
            send(error or "Serve il testo: /note 3 richiamare giovedì")
        else:
            store.add_note(lead["id"], args[1])
            send(f"Annotato su {lead['name']}.")

    elif command == "signature":
        if not rest:
            current = outreach.signature()
            send(f"Firma attuale:\n{current}" if current else
                 "Nessuna firma. Esempio:\n/signature Mohammad Nori - automazioni "
                 "per studi professionali, Pavia - 333 1234567")
        else:
            store.set_setting("signature", rest)
            send("Firma aggiornata. Ecco come chiuderanno le email:\n"
                 + outreach.email_footer())

    elif command == "add":
        fields = [f.strip() or None for f in rest.split("|")]
        if not fields or not fields[0]:
            send("Formato: /add Nome | Città | sito | telefono | email")
        else:
            fields += [None] * (5 - len(fields))
            name, city, website, phone, email = fields[:5]
            whatsapp = mobile_number(phone)
            lead_id = store.add_lead(name, city=city, website=website, phone=phone,
                                     email=email, whatsapp=whatsapp)
            send(f"Aggiunto [{lead_id}] {name}." if lead_id else f"{name} c'era già.")

    elif command == "source":
        from . import sourcing
        parts_ = rest.split()
        if not parts_:
            send("Come: /source dentisti Milano 200\n"
                 "Niche: " + ", ".join(sorted(sourcing.NICHES)))
            return True
        niche = parts_[0].lower()
        city = parts_[1].capitalize() if len(parts_) > 1 else "Milano"
        count = int(parts_[2]) if len(parts_) > 2 and parts_[2].isdigit() else 200
        send(f"🔎 Cerco {niche} a {city}...")

        def work():
            try:
                result = sourcing.import_niche(niche, city, count)
                send(sourcing.summarise(result, niche, city))
            except Exception as e:
                send(f"❌ {e}")

        threading.Thread(target=work, daemon=True).start()

    elif command == "import":
        added, skipped = 0, 0
        for line in rest.splitlines():
            line = line.strip()
            if not line:
                continue
            fields = [f.strip() or None for f in line.split("|")] + [None] * 5
            name, city, website, phone, email = fields[:5]
            if not name:
                continue
            if store.add_lead(name, city=city, website=website, phone=phone,
                              email=email, whatsapp=mobile_number(phone), source="import"):
                added += 1
            else:
                skipped += 1
        send(f"Importati {added} lead" + (f", {skipped} già presenti." if skipped else ".")
             + ("\n/scan per analizzarli." if added else ""))

    else:
        return False
    return True


def prune_screenshots(keep_days=30):
    """Screenshots are evidence for an opener, not an archive."""
    import time
    cutoff = time.time() - keep_days * 86400
    removed = 0
    if os.path.isdir(scanner.SHOTS_DIR):
        for name in os.listdir(scanner.SHOTS_DIR):
            path = os.path.join(scanner.SHOTS_DIR, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass
    return removed


def scan_pending(limit=10):
    """Scan leads that have never been scanned, and draft their openers."""
    pending = [l for l in store.list_leads(limit=store.LEADS_LIST_CAP)
              if not l["scanned_at"]][:limit]
    if not pending:
        return "Niente da scansionare."

    driver = None
    if os.environ.get("SCAN_MOBILE", "1") == "1":
        try:
            driver = scanner.browser()
        except Exception as e:
            print(f"   no browser for the mobile check: {e}")

    lines = []
    try:
        for lead in pending:
            findings, shot = scanner.scan_lead(lead, driver)
            draft = outreach.draft_opener(lead, findings) if findings else None
            store.save_scan(lead["id"], findings, draft)

            # Hand anything the cheap tier could not do to the brain queue,
            # which deploy/brain.sh drains when you next open a session.
            if findings and outreach.is_template_draft(draft):
                escalate("draft_needs_a_human",
                         f"{lead['name']}: the volume tier could not write an opener",
                         context={"lead_id": lead["id"], "name": lead["name"],
                                  "problems": [f["code"] for f in findings],
                                  "website": lead.get("website")},
                         priority="normal")
            lines.append(f"[{lead['id']}] {lead['name']}: "
                         + (outreach.describe(findings) if findings else "nessun problema trovato"))
    finally:
        if driver:
            driver.quit()

    pruned = prune_screenshots()
    if pruned:
        print(f"   removed {pruned} screenshot(s) older than 30 days")
    return "🔍 Scansione completata\n" + "\n".join(lines)
