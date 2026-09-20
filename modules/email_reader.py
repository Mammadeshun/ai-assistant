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

def _read_emails_via_composio(limit=15):
    """Read the inbox through Composio, which holds the Gmail OAuth grant.

    Nothing has to be generated in a browser on another machine and copied
    here, and there is no weekly token expiry to trip over.
    """
    from . import composio_mcp

    data = composio_mcp.execute(
        "GMAIL_FETCH_EMAILS",
        {"max_results": limit, "verbose": False, "include_payload": False},
        thought="fetch recent mail for the morning briefing",
        account=os.environ.get("COMPOSIO_GMAIL_ACCOUNT") or None)

    email_list = []
    for m in data.get("messages", []):
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
