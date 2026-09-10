import os
import json
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ── Tool definitions — Llama reads these to understand what it can do ──
TOOLS = [
    {
        "name": "kiro_check",
        "description": "Check Kiro UniPV for new course materials or announcements across all courses",
        "examples": ["what's new on kiro", "any new slides?", "check my courses"]
    },
    {
        "name": "kiro_list_courses",
        "description": "List all enrolled courses on Kiro UniPV",
        "examples": ["list my courses", "what courses am i enrolled in"]
    },
    {
        "name": "morning_routine",
        "description": "Run the full morning routine: clean PC, summarize emails, send briefing",
        "examples": ["good morning", "run morning routine", "summarize my emails", "clean my pc"]
    },
    {
        "name": "kiro_download",
        "description": "Download all files and PDFs from a specific course on Kiro",
        "examples": ["download ml slides", "get fuzzy systems files", "download everything from computer vision"],
        "params": ["course_name"]
    },
    {
        "name": "unknown",
        "description": "Used when the message doesn't match any available tool",
        "examples": []
    }
]

def build_prompt(user_message):
    tools_text = "\n".join([
        f"- {t['name']}: {t['description']} (e.g. {', '.join(t['examples'][:2]) if t['examples'] else 'N/A'})"
        for t in TOOLS
    ])

    return f"""You are an AI assistant controller. The user sent a message via Telegram.
Your job is to read the message and return a JSON object selecting the right tool and any parameters.

Available tools:
{tools_text}

Rules:
- Always respond with ONLY a raw JSON object, no explanation, no markdown.
- If the user mentions a course name, include it as "course_name" in params.
- If nothing matches, use "unknown" as the tool.

Examples:
User: "download the machine learning slides" → {{"tool": "kiro_download", "params": {{"course_name": "Machine Learning & Deep Learning"}}}}
User: "whats new on kiro" → {{"tool": "kiro_check", "params": {{}}}}
User: "good morning" → {{"tool": "morning_routine", "params": {{}}}}

User message: "{user_message}"
"""

def understand_message(user_message):
    """Uses Llama to parse a natural language message into a tool + params"""
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": build_prompt(user_message)}],
            model="llama-3.3-70b-versatile",
            temperature=0.0  # deterministic — we want consistent JSON
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if Llama wraps it anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        return result

    except Exception as e:
        print(f"❌ Agent error: {e}")
        return {"tool": "unknown", "params": {}}


if __name__ == "__main__":
    tests = [
        "what's new on kiro?",
        "download the fuzzy systems slides",
        "good morning",
        "list my courses",
        "what time is it",
    ]
    for msg in tests:
        result = understand_message(msg)
        print(f"'{msg}' → {result}")
