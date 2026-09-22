"""Call mode: one practice at a time, outcome in one tap, next one loads.

The step that was not happening was the calls, and the digest made them
feel like a list to work through rather than a thing to do now. This turns
it into a sequence: a card with the number (Telegram makes it tappable), the
problem found, and the opening line. Tap what happened; the next card
arrives. No typing, no ids to remember.

    /chiama   start
"""

from . import leads as store
from . import outreach
from . import telegram_bot

# Leads skipped in this session. Reset on restart, which is the right scope:
# "not now" should not mean "never".
_skipped = set()
_session = {"done": 0, "outcomes": {}}

BUTTONS = [
    [("✅ Parlato", "ok"), ("🔥 Interessato", "hot")],
    [("📵 Non risponde", "noanswer"), ("📅 Richiamare", "later")],
    [("❌ Non interessato", "no"), ("⏭ Salta", "skip")],
    [("⏹ Basta per oggi", "stop")],
]

OUTCOME_LABEL = {"ok": "✅ parlato", "hot": "🔥 interessato", "noanswer": "📵 non risponde",
                 "later": "📅 da richiamare", "no": "❌ non interessato", "skip": "⏭ saltato",
                 "wa_sent": "💬 messaggio inviato", "followed": "🔁 ricontattato"}


def _queue():
    return [l for l in store.due_leads()["to_call"] if l["id"] not in _skipped]


def wa_queue():
    """Leads to message first, worst problem first, each with a message that
    can actually be sent - a lead whose only finding is trivia has none."""
    return [l for l in store.due_leads()["to_whatsapp"]
            if l["id"] not in _skipped and outreach.whatsapp_message(l, store.findings_of(l))]


def _card(lead, remaining):
    findings = store.findings_of(lead)
    lines = [f"📞 {lead['name']}",
             f"    {lead.get('city') or ''} · {lead.get('category') or ''} · ne restano {remaining}",
             "",
             f"☎️ {lead['phone']}"]
    if findings:
        lines.append(f"🔎 {outreach.describe(findings) or findings[0]['code']}")
    if lead.get("website"):
        lines.append(f"🌐 {lead['website']}")
    if lead.get("attempts"):
        lines.append(f"↩️ tentativo n. {lead['attempts'] + 1}")
    draft = (lead.get("draft") or "").strip()
    if draft:
        lines += ["", "💬 Cosa dire:", draft[:600]]
    if lead.get("notes"):
        lines += ["", "📝 " + lead["notes"].splitlines()[-1][:200]]
    return "\n".join(lines)


def _buttons(lead_id):
    return [[(label, f"c:{lead_id}:{action}") for label, action in row] for row in BUTTONS]


def send_next():
    """Send the next card, or say the list is done."""
    queue = _queue()
    if not queue:
        summary = ", ".join(f"{OUTCOME_LABEL.get(k, k)} {v}"
                            for k, v in _session["outcomes"].items())
        telegram_bot.send_telegram_message(
            f"🏁 Lista chiamate finita per oggi. {_session['done']} gestite"
            + (f": {summary}." if summary else ".")
            + "\nChi non ha risposto torna domani.")
        return None
    lead = queue[0]
    return telegram_bot.send_with_buttons(_card(lead, len(queue) - 1), _buttons(lead["id"]))


def start(send):
    _skipped.clear()
    _session.update(done=0, outcomes={})
    queue = _queue()
    if not queue:
        send("Nessuna chiamata in coda oggi. /digest per il resto.")
        return
    send(f"📞 Modalità chiamate: {len(queue)} in coda, i problemi più gravi prima.\n"
         "Tocca il numero per chiamare, poi l'esito.")
    send_next()


def apply(lead_id, action, channel="call"):
    """Record what happened on a call or a WhatsApp chat. Returns a short
    label for the card.

    The note names the channel, and that matters beyond the history: the
    app's call counter counts notes that start with "chiamata", so a WhatsApp
    reply logged as one would inflate it.
    """
    lead = store.get(lead_id)
    if not lead:
        return "lead non trovato"
    via = {"whatsapp": "whatsapp", "email": "email"}.get(channel, "chiamata")
    if action == "wa_sent":
        store.set_state(lead_id, "WHATSAPP_SENT", note="whatsapp: inviato")
    elif action == "followed":
        store.mark_followed_up(lead_id)
    elif action == "ok":
        store.set_state(lead_id, "CONTACTED", note=f"{via}: parlato")
    elif action == "hot":
        store.set_state(lead_id, "INTERESTED", note=f"{via}: interessato")
    elif action == "later":
        store.set_state(lead_id, "CONTACTED", note=f"{via}: da richiamare")
        store.add_note(lead_id, "chiede di essere richiamato")
    elif action == "no":
        store.set_state(lead_id, "DEAD", note=f"{via}: non interessato")
    elif action == "noanswer":
        after = store.record_attempt(lead_id, "non risponde")
        if after and after["state"] == "DEAD":
            return f"📵 non risponde ({after['attempts']}° tentativo, archiviato)"
    elif action == "skip":
        _skipped.add(lead_id)
    return OUTCOME_LABEL.get(action, action)


def on_button(data, message_id, callback_id):
    """Handle a tap: record it, freeze the card, load the next one."""
    try:
        _, lead_id, action = data.split(":", 2)
        lead_id = int(lead_id)
    except ValueError:
        telegram_bot.answer_callback(callback_id, "?")
        return

    if action == "stop":
        telegram_bot.answer_callback(callback_id, "Ok, a domani")
        telegram_bot.edit_message(message_id, f"⏹ Pausa. {_session['done']} chiamate gestite oggi.")
        return

    lead = store.get(lead_id)
    label = apply(lead_id, action)
    if action != "skip":
        _session["done"] += 1
    _session["outcomes"][action] = _session["outcomes"].get(action, 0) + 1
    telegram_bot.answer_callback(callback_id, label)
    # Freeze the card: the outcome replaces the buttons, so a second tap on an
    # old card cannot record a second outcome.
    if lead:
        telegram_bot.edit_message(message_id, f"{lead['name']} · {lead['phone']}\n→ {label}")
    send_next()
