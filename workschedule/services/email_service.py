# Email sending service using Mailgun
import os
import requests

MAILGUN_DOMAIN = os.environ.get('MAILGUN_DOMAIN')
MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY')
REPLY_TO_ADDRESS = os.environ.get('MAILGUN_REPLY_TO', 'reply@myschedule.cloud')

def send_initial_email(recipient, subject, body):
	"""
	Sends an email via Mailgun to the recipient with a Reply-To header.
	"""
	return requests.post(
		f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
		auth=("api", MAILGUN_API_KEY),
		data={
			"from": f"MySchedule <noreply@{MAILGUN_DOMAIN}>",
			"to": [recipient],
			"subject": subject,
			"text": body,
			"h:Reply-To": REPLY_TO_ADDRESS
		}
	)
