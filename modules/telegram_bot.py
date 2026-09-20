import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# A send with no timeout once wedged the whole bot: one of Telegram's IPv6
# addresses stopped answering mid-connect, the socket sat in SYN-SENT forever,
# and the listener thread never came back - no reply, no error, no recovery
# until a restart. Anything that runs unattended needs a bound on every call.
REQUEST_TIMEOUT = 20  # seconds

_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=2,
    connect=2,              # a dead address gets retried, hitting the next one
    backoff_factor=1,
    allowed_methods=frozenset({"GET", "POST"}),
    status_forcelist=(502, 503, 504),
)))

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
        response = _session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
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
