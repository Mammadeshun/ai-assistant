#!/usr/bin/env bash
#
# Open a brain-tier session: Claude Opus on your subscription, handed whatever
# the cheap tier could not decide on its own.
#
#   ./deploy/brain.sh
#
# This is interactive on purpose. The subscription login cannot be scripted, so
# the brain never runs from a timer — it drains the queue when you show up.
# For unattended work use the volume tier (modules/llm.py). For interactive
# coding on cheaper models, point Claude Code at 9router (see deploy/README.md).

set -euo pipefail

cd "$(dirname "$0")/.."

QUEUE="${ESCALATION_QUEUE:-data/escalations.jsonl}"

if ! command -v claude >/dev/null 2>&1; then
  echo "claude not found. Install it with:" >&2
  echo "  curl -fsSL https://claude.ai/install.sh | bash" >&2
  exit 1
fi

echo "== Brain queue =="
python3 -m modules.escalate

if [[ ! -s "$QUEUE" ]] || ! python3 -c "
import sys
sys.path.insert(0, '.')
from modules.escalate import load_queue
sys.exit(0 if load_queue() else 1)
"; then
  echo
  echo "Nothing queued. Opening a normal session instead."
  exec claude
fi

echo
echo "Opening Claude with the queue as context..."
exec claude "Work the escalation queue in $QUEUE.

These are items the free volume tier flagged because it could not judge them
confidently. For each unresolved item: read the context, decide what should
happen, and either do it or tell me what you need. Mark each one resolved with
modules.escalate.resolve(item_id, note) as you finish it.

Start by reading $QUEUE and summarising what is waiting."
