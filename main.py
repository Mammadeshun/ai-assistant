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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")


# ──────────────────────────────────────────
# JOB FUNCTIONS
# ──────────────────────────────────────────

def run_morning_routine():
    print("Starting Morning Routine...\n")
    file_janitor.run_janitor()

    print("\n--- Scanning & Summarizing Emails ---")
    emails = email_reader.read_emails()

    if emails and len(emails) > 0:
        print("Thinking... Generating Llama 3 Summary...")
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

                # Let the AI agent decide what to do
                decision = understand_message(text)
                tool = decision.get("tool", "unknown")
                params = decision.get("params", {}) or {}

                print(f"🤖 Agent decision: {decision}")

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
    schedule.every().day.at("08:05").do(run_kiro_check)

    # Run Telegram listener in background thread
    listener_thread = threading.Thread(target=listen_for_commands, daemon=True)
    listener_thread.start()

    print("⏰ Scheduler running. Jobs at 08:00 & 08:05. Send natural messages to your bot!")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
