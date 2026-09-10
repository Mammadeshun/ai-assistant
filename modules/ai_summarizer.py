import os
from groq import Groq

# Paste your Groq API key here
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

def summarize_emails(email_list):
    if not email_list:
        return "No new emails to summarize."

    email_text = "\\n\\n".join([f"From: {e['from']}\\nSubject: {e['subject']}\\nBody Preview: {e['snippet']}" for e in email_list])
    
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
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content
        
    except Exception as e:
        print(f"Groq API Error: {e}")
        return "⚠️ Could not generate summary due to an AI error."

if __name__ == "__main__":
    test_data = [{"from": "prof@unipv.it", "subject": "Exam", "snippet": "The exam is moved to Monday."}]
    print(summarize_emails(test_data))
