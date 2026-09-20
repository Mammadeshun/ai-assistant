"""Minimal MCP client for Composio's connect.composio.dev endpoint.

Lives on its own so callers that only want to send mail do not drag in the
Google API client: importing email_reader pulls google-auth and friends, and
the Composio path needs none of it.

The consumer key (ck_...) authenticates here with an x-consumer-api-key
header. The platform key (ak_...) does NOT work against this endpoint, and
the v3 REST API rejects the consumer key just as firmly - they are separate
credentials for separate services.
"""

import os
import json

import requests

MCP_URL = os.environ.get("COMPOSIO_MCP_URL", "https://connect.composio.dev/mcp")
TIMEOUT = int(os.environ.get("COMPOSIO_TIMEOUT", "90"))


def _rpc(session, payload, headers, expect_reply=True):
    """One JSON-RPC call. Replies arrive as server-sent events, even single
    results, so the last `data:` line is the answer."""
    response = session.post(MCP_URL, headers=headers, json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    if not expect_reply:
        return response, None
    lines = [l[6:] for l in response.text.splitlines() if l.startswith("data: ")]
    if not lines:
        raise RuntimeError(f"no JSON-RPC reply: {response.text[:200]}")
    return response, json.loads(lines[-1])


def execute(tool_slug, arguments, thought, account=None):
    """Run one Composio tool and return its data payload.

    Raises RuntimeError with the provider's own message on failure, so the
    caller can put something useful in front of a human.
    """
    key = os.environ.get("COMPOSIO_CONSUMER_KEY")
    if not key:
        raise RuntimeError("COMPOSIO_CONSUMER_KEY is not set")

    headers = {"x-consumer-api-key": key, "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    session = requests.Session()

    response, _ = _rpc(session, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "ai-assistant", "version": "1"}}}, headers)
    if response.headers.get("mcp-session-id"):
        headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
    _rpc(session, {"jsonrpc": "2.0", "method": "notifications/initialized"},
         headers, expect_reply=False)

    call = {"tool_slug": tool_slug, "arguments": arguments}
    if account:
        call["account"] = account

    _, reply = _rpc(session, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "COMPOSIO_MULTI_EXECUTE_TOOL",
                   "arguments": {"thought": thought, "tools": [call]}}}, headers)

    if "error" in reply:
        raise RuntimeError(str(reply["error"])[:300])
    result = reply.get("result", {})
    text = "".join(c.get("text", "") for c in result.get("content", [])
                   if c.get("type") == "text")
    if result.get("isError"):
        raise RuntimeError(text[:300])

    inner = json.loads(text)["data"]["results"][0]["response"]
    if not inner.get("successful", False):
        raise RuntimeError(str(inner.get("error"))[:300])
    return inner.get("data", {})
