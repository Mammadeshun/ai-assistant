import os
import schedule
import time
import threading
import requests
from modules import file_janitor
from modules import email_reader
from modules import telegram_bot
from modules import ai_summarizer
from modules.kiro_scraper import check_kiro_updates, format_kiro_report, COURSES
from modules.ai_agent import understand_message
from modules import commands
from modules import leads as leads_store
from modules import outreach

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# Long-poll: Telegram holds the request open for POLL_SECONDS when there is
# nothing to deliver, so the read timeout has to comfortably exceed it.
POLL_SECONDS = 10
POLL_TIMEOUT = (10, POLL_SECONDS + 25)   # (connect, read)


def _redact(error):
    """Error text without the bot token in it.

    requests puts the full URL in its exceptions, and the token is part of the
    URL, so every network blip wrote the token into the journal - which /logs
    then forwards to Telegram.
    """
    text = str(error)
    return text.replace(TELEGRAM_BOT_TOKEN, "<token>") if TELEGRAM_BOT_TOKEN else text

# The Kiro/Moodle scraper stays dormant until its credentials are set. It is
# the only job that starts Chrome, and Chrome is the memory hog on a 4 GB box.
KIRO_ENABLED = bool(os.environ.get("UNIPV_USERNAME") and os.environ.get("UNIPV_PASSWORD"))


# ──────────────────────────────────────────
# JOB FUNCTIONS
# ──────────────────────────────────────────

def run_morning_routine():
    print("Starting Morning Routine...\n")
    file_janitor.run_janitor()

    print("\n--- Scanning & Summarizing Emails ---")
    emails = email_reader.read_emails()

    if emails is None:
        message = ("🤖 Good Morning!\n\n⚠️ I could not read your Gmail this "
                   "morning, so there is no briefing. Check the log:\n"
                   "  journalctl -u assistant -n 50")
    elif emails:
        print("Thinking... Generating summary...")
        ai_summary = ai_summarizer.summarize_emails(emails)
        message = f"🤖 Good Morning!\n\nHere is your AI Briefing:\n\n{ai_summary}"
    else:
        message = "🤖 Good Morning!\n\nYou have no new emails today."

    print("Sending AI summary to Telegram...")
    telegram_bot.send_telegram_message(message)
    print("\n✅ Morning routine complete!")


def run_kiro_check():
    print("\n📚 Running Kiro update check...")
    try:
        updates = check_kiro_updates()
        report = format_kiro_report(updates)

        if updates:
            chunks = [report[i:i+4000] for i in range(0, len(report), 4000)]
            for chunk in chunks:
                telegram_bot.send_telegram_message(chunk)
                time.sleep(1)
            print(f"   -> Kiro update sent! ({len(chunks)} message(s))")
        else:
            telegram_bot.send_telegram_message("🎓 Kiro: No new materials today.")
            print("   -> No new Kiro updates today.")
    except Exception as e:
        print(f"❌ Kiro job failed: {e}")


def run_lead_scan():
    """Overnight: scan whatever came in during the day and draft the openers.

    Sending is never part of this. The server prepares; you press send.
    """
    print("\n🔍 Running overnight lead scan...")
    try:
        summary = commands.scan_pending(limit=int(os.environ.get("SCAN_BATCH", "25")))
        print(summary)
    except Exception as e:
        print(f"❌ Lead scan failed: {e}")


def run_lead_digest():
    """The 08:10 list: who to call, what to send, in the order to do it."""
    print("\n📋 Building the lead digest...")
    try:
        moved = leads_store.advance_overdue()
        if moved:
            print(f"   {len(moved)} lead(s) moved to CALL_DUE: {moved}")

        buckets = leads_store.due_leads()
        actionable = sum(len(buckets[k]) for k in
                         ("to_whatsapp", "to_email", "to_call", "to_follow_up"))
        if not actionable:
            # A daily "nothing to do" trains you to ignore the digest, which
            # is the one message that must stay worth opening.
            print("   nothing actionable today, staying quiet")
            return

        message = outreach.format_digest(buckets, leads_store.counts())
        for chunk in [message[i:i + 4000] for i in range(0, len(message), 4000)]:
            telegram_bot.send_telegram_message(chunk)
            time.sleep(1)
    except Exception as e:
        print(f"❌ Lead digest failed: {e}")


# ──────────────────────────────────────────
# TELEGRAM AI AGENT LISTENER
# ──────────────────────────────────────────

def _drop_backlog():
    """Confirm whatever is queued, so a restart does not replay old messages.

    Telegram redelivers updates until they are confirmed by the next poll.
    Without this, restarting mid-command re-runs it, and a "good morning" sent
    while the service was down fires the routine again on boot.
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        data = requests.get(url, params={"timeout": 0, "offset": -1}, timeout=15).json()
        results = data.get("result", [])
        if results:
            last = results[-1]["update_id"]
            requests.get(url, params={"timeout": 0, "offset": last + 1}, timeout=15)
            print(f"   skipped {len(results)} message(s) queued while offline")
            return last + 1
    except Exception as e:
        print(f"   could not clear the backlog: {e}")
    return None


def listen_for_commands():
    print("💬 Telegram AI listener active...")
    last_update_id = _drop_backlog()
    warned_conflict = False

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": POLL_SECONDS, "offset": last_update_id}
            response = requests.get(url, params=params, timeout=POLL_TIMEOUT).json()

            # Telegram gives one update to one poller. A second instance - the
            # laptop copy, typically - silently steals half the messages, and
            # the only visible sign is this error code.
            if not response.get("ok"):
                description = str(response.get("description", ""))
                if response.get("error_code") == 409 and not warned_conflict:
                    print("⚠️  409 Conflict: another instance is polling this bot "
                          "token. Messages will be split between them.")
                    warned_conflict = True
                elif response.get("error_code") != 409:
                    print(f"⚠️  Telegram refused getUpdates: {description[:120]}")

            for update in response.get("result", []):
                last_update_id = update["update_id"] + 1

                # A button tap on a call card.
                callback = update.get("callback_query")
                if callback:
                    chat = str(callback.get("message", {}).get("chat", {}).get("id", ""))
                    if chat != TELEGRAM_CHAT_ID:
                        continue
                    try:
                        from modules import callmode
                        callmode.on_button(callback.get("data", ""),
                                           callback["message"]["message_id"], callback["id"])
                    except Exception as e:
                        print(f"❌ Button failed: {_redact(e)}")
                    continue

                message = update.get("message", {})
                text = message.get("text", "").strip()
                chat_id = str(message.get("chat", {}).get("id", ""))

                if chat_id != TELEGRAM_CHAT_ID:
                    continue

                print(f"📩 Message from you: {text}")

                # Slash commands are parsed literally. "/dead 12" must mean
                # that every time, with no model in the loop.
                if text.startswith("/"):
                    # The two scheduled jobs live here rather than in
                    # commands.py, which cannot import main without a cycle.
                    literal = text.split()[0].lstrip("/").lower()
                    if literal in ("briefing", "morning_routine"):
                        telegram_bot.send_telegram_message("⏳ Preparo il briefing...")
                        threading.Thread(target=run_morning_routine, daemon=True).start()
                        continue
                    if literal in ("kiro", "kiro_check"):
                        if KIRO_ENABLED:
                            telegram_bot.send_telegram_message("⏳ Controllo Kiro...")
                            threading.Thread(target=run_kiro_check, daemon=True).start()
                        else:
                            telegram_bot.send_telegram_message(
                                "📚 Kiro è spento: mancano UNIPV_USERNAME e UNIPV_PASSWORD.")
                        continue
                    try:
                        if commands.handle(text, telegram_bot.send_telegram_message):
                            continue
                    except Exception as e:
                        print(f"❌ Command failed: {e}")
                        telegram_bot.send_telegram_message(f"❌ {e}")
                        continue

                # Otherwise let the model map free text onto a command.
                decision = understand_message(text)
                print(f"🤖 Agent decision: {decision}")

                if decision.get("reply"):
                    telegram_bot.send_telegram_message(decision["reply"])
                    continue

                command = decision.get("command", "")
                name = command.split()[0].lstrip("/").lower() if command else ""

                if name in commands.SAFE:
                    # Read-only: just do it.
                    try:
                        if not commands.handle(command, telegram_bot.send_telegram_message):
                            telegram_bot.send_telegram_message(
                                "Non ho capito. /help per l'elenco dei comandi.")
                    except Exception as e:
                        print(f"❌ Command failed: {e}")
                        telegram_bot.send_telegram_message(f"❌ {e}")
                elif name in ("briefing", "morning_routine"):
                    telegram_bot.send_telegram_message("⏳ Preparo il briefing...")
                    threading.Thread(target=run_morning_routine, daemon=True).start()
                elif name.startswith("kiro"):
                    if KIRO_ENABLED:
                        telegram_bot.send_telegram_message("⏳ Controllo Kiro...")
                        threading.Thread(target=run_kiro_check, daemon=True).start()
                    else:
                        telegram_bot.send_telegram_message(
                            "📚 Kiro è spento: mancano UNIPV_USERNAME e UNIPV_PASSWORD.")
                elif name:
                    # Anything that sends, changes state or restarts a service
                    # is confirmed by a human. A misread sentence must not be
                    # able to email a business or mark a lead dead.
                    telegram_bot.send_telegram_message(
                        f"Intendi questo?\n\n{command}\n\nToccalo per confermare.")
                else:
                    telegram_bot.send_telegram_message(
                        "Non ho capito. /help per l'elenco dei comandi.")

        except requests.exceptions.ReadTimeout:
            # A long-poll that timed out is not an error: nothing arrived.
            # Logging these (86 in two days) buried the real failures.
            continue
        except Exception as e:
            print(f"⚠️ Listener error: {_redact(e)}")

        time.sleep(2)


# ──────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────

def main():
    print("🤖 AI Assistant started!\n")

    # Schedule daily jobs
    schedule.every().day.at("08:00").do(run_morning_routine)
    if KIRO_ENABLED:
        schedule.every().day.at("08:05").do(run_kiro_check)
    # Leads: scan overnight when nobody is waiting, then hand you the list at
    # breakfast. Both times are local, which is why the box runs Europe/Rome.
    schedule.every().day.at(os.environ.get("SCAN_AT", "03:00")).do(run_lead_scan)
    schedule.every().day.at(os.environ.get("DIGEST_AT", "08:10")).do(run_lead_digest)

    # The "/" menu on the phone: commands you can see beat commands you must
    # remember, and this is the list people actually use.
    telegram_bot.set_commands([
        ("chiama", "Chiamate: un lead alla volta, esito con un tocco"),
        ("digest", "Chi chiamare e cosa inviare oggi"),
        ("status", "Server, modelli, lead, backup"),
        ("sito", "Visite di switchers.events e Google"),
        ("briefing", "Riassunto della posta, ora"),
        ("leads", "Elenco dei lead"),
        ("source", "Cerca nuove attività: /source dentisti Milano"),
        ("logs", "Ultime righe di log"),
        ("help", "Tutti i comandi"),
    ])

    # Run Telegram listener in background thread
    listener_thread = threading.Thread(target=listen_for_commands, daemon=True)
    listener_thread.start()

    jobs = ["08:00 briefing"]
    if KIRO_ENABLED:
        jobs.append("08:05 kiro")
    jobs += [f"{os.environ.get('SCAN_AT', '03:00')} lead scan",
             f"{os.environ.get('DIGEST_AT', '08:10')} lead digest"]
    print("⏰ Scheduler running: " + ", ".join(jobs))
    print("   Slash commands: /help. Natural messages go to the agent.")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
