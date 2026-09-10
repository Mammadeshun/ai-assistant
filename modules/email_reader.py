import os
import datetime
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
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def read_emails():
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
        print(f'An error occurred: {error}')
        return []

if __name__ == '__main__':
    print(read_emails())
