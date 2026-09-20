"""Turn anything you type into either a command or an answer.

The bot should understand "come vanno i lead?" as readily as "/leads", so
this asks the volume tier to map free text onto the command catalogue.

Two rules keep that safe:

  * Read-only commands run immediately.
  * Anything with consequences - sending an email, changing a lead's state,
    restarting a service - comes back as a command for you to tap. A model
    misreading a sentence must not be able to email a business.

When nothing fits, it answers in plain language instead of reciting a menu.
"""

from .llm import ask_volume_json, VolumeLLMError
from .commands import CATALOGUE

SYSTEM = """Sei il router di un assistente personale su Telegram.
L'utente scrive in italiano o in inglese, in modo informale.

Rispondi SOLO con un oggetto JSON, senza markdown:
  {"command": "/leads"}            per eseguire un comando
  {"reply": "..."}                 per rispondere a voce, se nessun comando serve

Regole:
- Scegli un comando solo se esiste nell'elenco. Non inventarne.
- Includi gli argomenti nel comando, es. {"command": "/lead 3"}.
- Se manca un dato indispensabile (per esempio quale lead), chiedilo con "reply".
- Se l'utente fa una domanda generica o chiacchiera, usa "reply" e sii breve.
- "reply" è in italiano se l'utente scrive in italiano."""


def build_prompt(user_message):
    catalogue = "\n".join(f"  {name} - {what}" for name, what in CATALOGUE)
    return f"""Comandi disponibili:
{catalogue}

Messaggio dell'utente: "{user_message}"

JSON:"""


def understand_message(user_message):
    """Return {"command": "/x"} or {"reply": "..."}.

    Falls back to a reply rather than an error: an assistant that says
    nothing useful when the model is capped is worse than a slow one.
    """
    try:
        result = ask_volume_json(build_prompt(user_message), system=SYSTEM, max_tokens=400)
    except VolumeLLMError as e:
        print(f"❌ Agent error: {e}")
        return {"reply": "Non riesco a ragionare in questo momento (modelli non "
                         "disponibili). I comandi diretti funzionano lo stesso: /help"}
    except Exception as e:
        print(f"❌ Agent error: {e}")
        return {"reply": "Qualcosa è andato storto nel capire il messaggio. /help"}

    if not isinstance(result, dict):
        return {"reply": "Non ho capito. Prova con /help"}

    command = result.get("command")
    if isinstance(command, str) and command.strip().startswith("/"):
        return {"command": command.strip()}
    reply = result.get("reply")
    if isinstance(reply, str) and reply.strip():
        return {"reply": reply.strip()}
    return {"reply": "Non ho capito. Prova con /help"}


if __name__ == "__main__":
    for message in ("come vanno i lead?", "come sta il server?",
                    "mandagli la mail al 3", "che novità ci sono stamattina?",
                    "ciao come stai?", "fammi vedere il lead numero 5"):
        print(f"{message!r:40} -> {understand_message(message)}")
