import os
import sys
import json
import datetime
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def authenticate_gmail():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # run_local_server() opens a browser and then blocks forever
            # waiting for a redirect. Under systemd there is no browser and
            # no tty, so refuse instead of hanging the morning routine.
            if not sys.stdin.isatty():
                raise RuntimeError(
                    "token.json is missing or unusable, and Gmail's login "
                    "needs a browser. Generate it on your laptop and copy it "
                    "over - see deploy/README.md."
                )
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

COMPOSIO_MCP_URL = os.environ.get("COMPOSIO_MCP_URL", "https://connect.composio.dev/mcp")
COMPOSIO_TIMEOUT = 90


def _composio_rpc(session, payload, headers, expect_reply=True):
    """One JSON-RPC call over MCP's streamable HTTP transport.

    Replies come back as server-sent events (`data: {...}`) even for a single
    result, so the last data line is the answer.
    """
    response = session.post(COMPOSIO_MCP_URL, headers=headers, json=payload,
                            timeout=COMPOSIO_TIMEOUT)
    response.raise_for_status()
    if not expect_reply:
        return response, None
    lines = [l[6:] for l in response.text.splitlines() if l.startswith("data: ")]
    if not lines:
        raise RuntimeError(f"no JSON-RPC reply: {response.text[:200]}")
    return response, json.loads(lines[-1])


def _read_emails_via_composio(limit=15):
    """Read the inbox through Composio's MCP endpoint.

    Composio holds the Gmail OAuth grant, so nothing has to be generated in a
    browser on another machine and copied here, and there is no weekly token
    expiry to trip over.

    The consumer key (ck_...) authenticates against connect.composio.dev with
    an x-consumer-api-key header. It is NOT the platform API key (ak_...) and
    every v3 REST endpoint rejects it, which is a confusing thing to debug -
    hence this going over MCP rather than the SDK.
    """
    key = os.environ["COMPOSIO_CONSUMER_KEY"]
    account = os.environ.get("COMPOSIO_GMAIL_ACCOUNT", "")

    headers = {
        "x-consumer-api-key": key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    session = requests.Session()

    response, _ = _composio_rpc(session, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "ai-assistant", "version": "1"}},
    }, headers)
    session_id = response.headers.get("mcp-session-id")
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    _composio_rpc(session, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  headers, expect_reply=False)

    call = {"tool_slug": "GMAIL_FETCH_EMAILS",
            "arguments": {"max_results": limit, "verbose": False,
                          "include_payload": False}}
    if account:
        # Required when several mailboxes are connected; without it Composio
        # picks its default, which may be the wrong inbox.
        call["account"] = account

    _, reply = _composio_rpc(session, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "COMPOSIO_MULTI_EXECUTE_TOOL",
                   "arguments": {"thought": "fetch recent mail for the morning briefing",
                                 "tools": [call]}},
    }, headers)

    if "error" in reply:
        raise RuntimeError(reply["error"])
    result = reply.get("result", {})
    if result.get("isError"):
        raise RuntimeError(str(result.get("content"))[:300])

    text = "".join(c.get("text", "") for c in result.get("content", [])
                   if c.get("type") == "text")
    inner = json.loads(text)["data"]["results"][0]["response"]
    if not inner.get("successful", False):
        raise RuntimeError(inner.get("error") or "Composio reported failure")

    email_list = []
    for m in inner.get("data", {}).get("messages", []):
        preview = m.get("preview") if isinstance(m.get("preview"), dict) else {}
        email_list.append({
            "subject": m.get("subject") or preview.get("subject") or "No Subject",
            "from": m.get("sender") or "Unknown Sender",
            "snippet": preview.get("body") or m.get("messageText") or "No preview available.",
        })
        print(f" - Found: {email_list[-1]['subject'][:70]}")
    return email_list


def read_emails():
    """Return a list of emails, or None if the mailbox could not be read.

    None and [] mean different things here: [] is a genuinely empty inbox,
    None is a failure, and the morning briefing reports them differently.
    """
    if os.environ.get("COMPOSIO_CONSUMER_KEY"):
        try:
            return _read_emails_via_composio()
        except Exception as error:
            print(f'Composio Gmail failed: {error}')
            return None
    return _read_emails_via_token()


def _read_emails_via_token():
    try:
        service = authenticate_gmail()
        # Grabbing the top 15 emails to ensure we don't miss university stuff under spam
        results = service.users().messages().list(userId='me', maxResults=15).execute()
        messages = results.get('messages', [])

        if not messages:
            print('No messages found.')
            return []

        email_list = []
        for msg in messages:
            msg_id = msg['id']
            message = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Subject', 'From']).execute()
            
            headers = message['payload']['headers']
            subject = next((header['value'] for header in headers if header['name'] == 'Subject'), 'No Subject')
            sender = next((header['value'] for header in headers if header['name'] == 'From'), 'Unknown Sender')
            
            # This grabs the actual text inside the email for the AI to read!
            snippet = message.get('snippet', 'No preview available.')
            
            email_list.append({'subject': subject, 'from': sender, 'snippet': snippet})
            print(f" - Found: {subject}")
            
        return email_list

    except Exception as error:
        # None means "I could not read the mailbox", which is a different
        # thing from "the mailbox is empty". The caller must not report an
        # empty inbox when the truth is that Gmail failed.
        print(f'An error occurred: {error}')
        return None

if __name__ == '__main__':
    # python -m modules.email_reader
    print(read_emails())
