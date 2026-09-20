"""Volume-tier LLM calls, with fall-through across free providers.

Two tiers run in this project and they are deliberately not interchangeable:

  volume tier  — free models (Groq, Gemini). Unattended, on the server, high
                 throughput, low stakes. Everything in this file.
  brain tier   — Claude Opus via the subscription. Interactive only, because
                 the subscription login cannot be scripted. It never runs from
                 a timer; it picks work up from the escalation queue instead
                 (see modules/escalate.py).

Free tiers have daily and per-minute caps, so a single provider will stop
answering partway through a long unattended run. The router does the same thing
for Claude Code: when one model hits a limit, move to the next. ask_volume()
walks the chain below and only gives up once every link has refused.

Anything here that needs real judgement should call escalate() rather than
reaching for a bigger model.
"""

import os
import json
import time
import requests

DEFAULT_TIMEOUT = 60

# Tried in order. A 429 (rate limit) or 5xx moves to the next link; a 4xx that
# isn't 429 is a real error and stops the walk, because retrying a malformed
# request against three providers just wastes three providers.
#
# Override the whole chain with VOLUME_CHAIN as JSON if you want a different
# order, or point VOLUME_BASE_URL at the local router to send everything
# through it instead.
DEFAULT_CHAIN = [
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
    },
    {
        "name": "gemini",
        # Gemini speaks an OpenAI-compatible dialect, so one code path covers both.
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "model": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
    },
    {
        # Same provider, smaller model. Groq meters per-model, so this often
        # still answers when the big Llama is capped for the day.
        "name": "groq-small",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": os.environ.get("GROQ_SMALL_MODEL", "llama-3.1-8b-instant"),
    },
]


class VolumeLLMError(RuntimeError):
    """Every link in the chain refused, or one refused unrecoverably."""


def _chain():
    override = os.environ.get("VOLUME_CHAIN", "").strip()
    if override:
        try:
            return json.loads(override)
        except json.JSONDecodeError:
            print("⚠️  VOLUME_CHAIN is not valid JSON, using the default chain.")

    base_url = os.environ.get("VOLUME_BASE_URL", "").strip().rstrip("/")
    if base_url:
        return [{
            "name": "router",
            "base_url": base_url,
            "key_env": "VOLUME_API_KEY",
            "model": os.environ.get("VOLUME_MODEL", "default"),
        }]

    return DEFAULT_CHAIN


def _call(link, messages, max_tokens, temperature):
    """One attempt against one provider. Returns (text, retryable_reason)."""
    api_key = os.environ.get(link.get("key_env", ""), "")
    if not api_key and link.get("name") != "router":
        return None, f"{link['name']}: no API key set ({link.get('key_env')})"

    try:
        response = requests.post(
            f"{link['base_url'].rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                # 9router applies Caveman/Ponytail to every request that passes
                # through it, by injecting system prompts. That suits a coding
                # CLI; it mangles an Italian briefing or a client-facing draft.
                # Providers that aren't the router ignore an unknown X- header.
                "X-9Router-Token-Saver": "off",
            },
            json={
                "model": link["model"],
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as e:
        return None, f"{link['name']}: unreachable ({e})"

    if response.status_code == 200:
        try:
            return response.json()["choices"][0]["message"]["content"], None
        except (KeyError, IndexError, ValueError) as e:
            return None, f"{link['name']}: unexpected response shape ({e})"

    if response.status_code == 429 or response.status_code >= 500:
        return None, f"{link['name']}: HTTP {response.status_code} (limit or outage)"

    # A 400/401/403 is our fault, not the provider's capacity. Stop the walk.
    raise VolumeLLMError(
        f"{link['name']} rejected the request with HTTP {response.status_code}: "
        f"{response.text[:300]}"
    )


def ask_volume(prompt, system=None, max_tokens=1024, temperature=0.2, pause=1.0):
    """Send a prompt to the cheap tier, falling through the chain on limits."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    reasons = []
    for i, link in enumerate(_chain()):
        text, reason = _call(link, messages, max_tokens, temperature)
        if text is not None:
            if i:
                print(f"   -> volume tier fell through to {link['name']}")
            return text
        reasons.append(reason)
        print(f"   -> {reason}, trying next provider")
        if pause:
            time.sleep(pause)

    raise VolumeLLMError("whole volume chain refused: " + "; ".join(reasons))


def ask_volume_json(prompt, system=None, max_tokens=1024):
    """Same, but insist on a JSON object back.

    Free models wander outside the fence, so the text is salvaged between the
    first '{' and the last '}' before parsing.
    """
    raw = ask_volume(prompt, system=system, max_tokens=max_tokens, temperature=0)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise VolumeLLMError(f"no JSON object in response: {raw[:200]}")
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError as e:
        raise VolumeLLMError(f"malformed JSON from volume tier: {e}") from e


if __name__ == "__main__":
    print(ask_volume("Reply with exactly: ok"))
