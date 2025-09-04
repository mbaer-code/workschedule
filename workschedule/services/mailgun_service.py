import os
import requests
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

def send_simple_message(to_email, subject, text_content, html_content=None):
    """
    Sends an email using the Mailgun API.
    
    Args:
        to_email (str): The recipienta's email address.
        subject (str): The subject of the email.
        text_content (str): The plain text body of the email.
        html_content (str): Optional HTML body of the email.

    Returns:
        bool: True if the email was sent successfully, False otherwise.
    """
    mailgun_api_key = os.getenv("MAILGUN_API_KEY")
    mailgun_domain = os.getenv("MAILGUN_DOMAIN")

    if not mailgun_api_key or not mailgun_domain:
        print("Error: Mailgun API key or domain is not set in environment variables.")
        return False

    api_url = f"https://api.mailgun.net/v3/{mailgun_domain}/messages"
    
    data = {
        "from": f"Schedule to ICS <mailgun@{mailgun_domain}>",
        "to": to_email,
        "subject": subject,
        "text": text_content
    }

    if html_content:
        data["html"] = html_content

    try:
        response = requests.post(
            api_url,
            auth=("api", mailgun_api_key),
            data=data
        )
        response.raise_for_status()  # Raises an HTTPError for bad responses
        print(f"Email sent successfully to {to_email}. Status code: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False

