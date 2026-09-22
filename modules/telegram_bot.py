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
        # The token is in the URL, and requests puts the URL in its errors.
        print(f"Telegram connection error: {str(e).replace(BOT_TOKEN, '<token>') if BOT_TOKEN else e}")

def send_telegram_photo(path, caption=""):
    """Send an image - the evidence an opener refers to.

    Captions are capped at 1024 characters by Telegram, so a long draft goes
    as a separate message rather than being silently truncated.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as photo:
            response = _session.post(url, data={"chat_id": CHAT_ID,
                                                "caption": caption[:1024]},
                                     files={"photo": photo},
                                     timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            print("📱 Screenshot sent!")
            return True
        print(f"Failed to send screenshot: {response.text[:200]}")
    except OSError as e:
        print(f"Screenshot not readable: {e}")
    except Exception as e:
        # The token is in the URL, and requests puts the URL in its errors.
        print(f"Telegram connection error: {str(e).replace(BOT_TOKEN, '<token>') if BOT_TOKEN else e}")
    return False


def _api(method, payload):
    """One Bot API call; returns the result object or None."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        response = _session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        data = response.json()
        if not data.get("ok"):
            print(f"Telegram {method} refused: {str(data.get('description'))[:150]}")
            return None
        return data.get("result")
    except Exception as e:
        print(f"Telegram {method} error: {str(e).replace(BOT_TOKEN, '<token>') if BOT_TOKEN else e}")
        return None


def send_with_buttons(text, rows):
    """Send a message with inline buttons. rows = [[(label, data), ...], ...].

    Returns the message id so the card can be edited in place once a button
    is pressed, instead of stacking a new message per tap.
    """
    keyboard = {"inline_keyboard": [[{"text": label, "callback_data": data}
                                     for label, data in row] for row in rows]}
    result = _api("sendMessage", {"chat_id": CHAT_ID, "text": text,
                                  "reply_markup": keyboard})
    return result.get("message_id") if result else None


def edit_message(message_id, text):
    """Replace a card's text and drop its buttons, so it cannot be tapped twice."""
    return _api("editMessageText", {"chat_id": CHAT_ID, "message_id": message_id,
                                    "text": text})


def answer_callback(callback_id, text=""):
    """Stop the button's loading spinner; Telegram shows it until answered."""
    return _api("answerCallbackQuery", {"callback_query_id": callback_id,
                                        "text": text[:190]})


def set_commands(commands):
    """Populate the '/' menu, so the commands are discoverable on the phone
    instead of living in a message you have to scroll back to find."""
    return _api("setMyCommands", {"commands": [
        {"command": name, "description": desc[:250]} for name, desc in commands]})


# Let's test it immediately!
if __name__ == "__main__":
    test_msg = "🤖 Hello! I am your Python Assistant.\n\nYour PC cleanup is done and I am watching your emails!"
    send_telegram_message(test_msg)
