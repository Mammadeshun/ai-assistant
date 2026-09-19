"""The hand-off from the volume tier to the brain.

The Claude subscription cannot run unattended — its login is interactive — so
the brain does not poll for work. Instead the cheap tier writes anything it
can't confidently judge to a queue, and the brain drains that queue the next
time you open a session:

    ssh agent@server
    cd /opt/ai-assistant && ./deploy/brain.sh

Each line of data/escalations.jsonl is one item. Nothing is ever deleted on
read; items are marked resolved so the history stays auditable.
"""

import os
import json
import uuid
import datetime

QUEUE_FILE = os.environ.get("ESCALATION_QUEUE", "data/escalations.jsonl")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def escalate(kind, summary, context=None, priority="normal"):
    """Queue something for the brain tier.

    kind      short machine-ish label, e.g. "lead_ambiguous", "scraper_broke"
    summary   one line a human can read on a phone
    context   any JSON-serialisable detail the brain will need
    priority  "low" | "normal" | "high"
    """
    os.makedirs(os.path.dirname(QUEUE_FILE) or ".", exist_ok=True)

    item = {
        "id": uuid.uuid4().hex[:8],
        "created_at": _now(),
        "kind": kind,
        "summary": summary,
        "context": context or {},
        "priority": priority,
        "resolved": False,
    }

    with open(QUEUE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"🧠 Escalated to brain [{item['id']}] {summary}")
    return item["id"]


def load_queue(include_resolved=False):
    """Read the queue. Malformed lines are skipped rather than fatal."""
    if not os.path.exists(QUEUE_FILE):
        return []

    items = []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if include_resolved or not item.get("resolved"):
                items.append(item)

    order = {"high": 0, "normal": 1, "low": 2}
    items.sort(key=lambda i: (order.get(i.get("priority"), 1), i.get("created_at", "")))
    return items


def resolve(item_id, note=None):
    """Mark one item done. Rewrites the file in place."""
    if not os.path.exists(QUEUE_FILE):
        return False

    lines, found = [], False
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                lines.append(line)
                continue
            if item.get("id") == item_id and not item.get("resolved"):
                item["resolved"] = True
                item["resolved_at"] = _now()
                if note:
                    item["resolution_note"] = note
                found = True
            lines.append(json.dumps(item, ensure_ascii=False))

    if found:
        tmp = QUEUE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, QUEUE_FILE)

    return found


def format_queue(items=None):
    """Render the queue for Telegram or a terminal."""
    items = load_queue() if items is None else items
    if not items:
        return "🧠 Brain queue is empty — the cheap tier handled everything."

    marks = {"high": "🔴", "normal": "🟡", "low": "⚪"}
    out = [f"🧠 Brain queue — {len(items)} item(s)", "━" * 28]
    for item in items:
        out.append(
            f"\n{marks.get(item.get('priority'), '🟡')} [{item['id']}] "
            f"{item.get('kind', '?')}\n   {item.get('summary', '')}"
        )
    return "\n".join(out)


if __name__ == "__main__":
    print(format_queue())
