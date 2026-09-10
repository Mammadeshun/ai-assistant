import os
import requests

# From the environment - never hardcode this, the repo is public
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# From the environment (userinfobot gives you the chat id)
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram_message(message):
    """Sends a raw text message to your phone via Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # We removed parse_mode so Telegram accepts all characters safely
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("📱 Telegram message sent successfully!")
        else:
            print(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        print(f"Telegram connection error: {e}")

# Let's test it immediately!
if __name__ == "__main__":
    test_msg = "🤖 Hello! I am your Python Assistant.\n\nYour PC cleanup is done and I am watching your emails!"
    send_telegram_message(test_msg)
