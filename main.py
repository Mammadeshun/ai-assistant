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
    """The 08:00 list: who to call, what to send, in the order to do it."""
    print("\n📋 Building the lead digest...")
    try:
        message = outreach.format_digest(leads_store.due_leads(), leads_store.counts())
        for chunk in [message[i:i + 4000] for i in range(0, len(message), 4000)]:
            telegram_bot.send_telegram_message(chunk)
            time.sleep(1)
    except Exception as e:
        print(f"❌ Lead digest failed: {e}")


# ──────────────────────────────────────────
# TELEGRAM AI AGENT LISTENER
# ──────────────────────────────────────────

def listen_for_commands():
    print("💬 Telegram AI listener active...")
    last_update_id = None

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": 10, "offset": last_update_id}
            response = requests.get(url, params=params, timeout=15).json()

            for update in response.get("result", []):
                last_update_id = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "").strip()
                chat_id = str(message.get("chat", {}).get("id", ""))

                if chat_id != TELEGRAM_CHAT_ID:
                    continue

                print(f"📩 Message from you: {text}")

                # Slash commands are parsed literally. "/dead 12" must mean
                # that every time, with no model in the loop.
                if text.startswith("/"):
                    try:
                        if commands.handle(text, telegram_bot.send_telegram_message):
                            continue
                    except Exception as e:
                        print(f"❌ Command failed: {e}")
                        telegram_bot.send_telegram_message(f"❌ {e}")
                        continue

                # Otherwise let the AI agent decide what to do
                decision = understand_message(text)
                tool = decision.get("tool", "unknown")
                params = decision.get("params", {}) or {}

                print(f"🤖 Agent decision: {decision}")

                if tool.startswith("kiro") and not KIRO_ENABLED:
                    telegram_bot.send_telegram_message(
                        "📚 Kiro is switched off on the server. Set "
                        "UNIPV_USERNAME and UNIPV_PASSWORD in .env and restart "
                        "the assistant to turn it back on."
                    )
                    continue

                if tool == "morning_routine":
                    telegram_bot.send_telegram_message("⏳ Running morning routine...")
                    threading.Thread(target=run_morning_routine).start()

                elif tool == "kiro_check":
                    telegram_bot.send_telegram_message("⏳ Checking Kiro for new materials...")
                    threading.Thread(target=run_kiro_check).start()

                elif tool == "kiro_list_courses":
                    courses_text = "\n".join([f"• {name}" for name in COURSES.keys()])
                    telegram_bot.send_telegram_message("📚 Your Kiro courses:\n" + courses_text)

                elif tool == "kiro_download":
                    course_name = params.get("course_name")
                    if not course_name:
                        telegram_bot.send_telegram_message("❓ Which course? e.g. 'download fuzzy systems slides'")
                    else:
                        telegram_bot.send_telegram_message(f"⏳ Downloading files from {course_name}... (coming soon)")

                else:
                    telegram_bot.send_telegram_message(
                        "🤔 I didn't understand. Try:\n\n"
                        "• 'what's new on kiro?'\n"
                        "• 'download fuzzy systems slides'\n"
                        "• 'good morning'\n"
                        "• 'list my courses'"
                    )

        except Exception as e:
            print(f"⚠️ Listener error: {e}")

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
