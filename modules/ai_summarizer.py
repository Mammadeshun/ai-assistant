"""The morning briefing: 15 emails in, a few useful lines out.

Model calls go through modules/llm.py, which points at 9router. No provider
SDK and no API key in here on purpose - the router owns the accounts.
"""

from .llm import ask_volume, VolumeLLMError

def summarize_emails(email_list):
    if not email_list:
        return "No new emails to summarize."

    email_text = "\n\n".join(
        f"From: {e['from']}\nSubject: {e['subject']}\nBody Preview: {e['snippet']}"
        for e in email_list
    )
    
    prompt = f"""
    You are my brilliant personal AI assistant. I am a university student in Pavia, Italy.
    I am giving you my 15 most recent emails. 
    
    Your exact instructions:
    1. IGNORE all promotional spam, Indeed job alerts, newsletters, and receipts.
    2. FIND the important emails, especially anything from Università di Pavia, professors, or real humans.
    3. Write a clean, natural summary of ONLY the important emails. Give me actionable bullet points.
    4. If there is nothing important at all, just reply EXACTLY with: "No important emails today, just spam and alerts."
    5. Do not use Markdown symbols (like * or **). Just use plain text and emojis.
    
    Here are the emails:
    {email_text}
    """

    try:
        return ask_volume(prompt, max_tokens=1024)
    except VolumeLLMError as e:
        print(f"Volume tier error: {e}")
        return "⚠️ Could not generate summary due to an AI error."

if __name__ == "__main__":
    test_data = [{"from": "prof@unipv.it", "subject": "Exam", "snippet": "The exam is moved to Monday."}]
    print(summarize_emails(test_data))
