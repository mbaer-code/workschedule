import os
import requests
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

def send_simple_message(to_email, subject, text_content, html_content=None, attachment_bytes=None, attachment_filename=None):
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
    import sys
    mailgun_api_key = os.getenv("MAILGUN_API_KEY")
    mailgun_domain = os.getenv("MAILGUN_DOMAIN")

    sys.stderr.write(f"[Mailgun] Preparing to send email. to_email={to_email}, subject={subject}, mailgun_domain={mailgun_domain}\n")
    if not mailgun_api_key or not mailgun_domain:
        sys.stderr.write("[Mailgun] Error: Mailgun API key or domain is not set in environment variables.\n")
        return False

    api_url = f"https://api.mailgun.net/v3/{mailgun_domain}/messages"
    sys.stderr.write(f"[Mailgun] API URL: {api_url}\n")
    data = {
        "from": f"Schedule to ICS <mailgun@{mailgun_domain}>",
        "to": to_email,
        "subject": subject,
        "text": text_content
    }

    if html_content:
        data["html"] = html_content

    files = None
    if attachment_bytes and attachment_filename:
        files = [
            ("attachment", (attachment_filename, attachment_bytes, "text/calendar"))
        ]

    sys.stderr.write(f"[Mailgun] Data: {data}\n")
    if files:
        sys.stderr.write(f"[Mailgun] Attachment: {attachment_filename}, bytes={len(attachment_bytes)}\n")
    try:
        response = requests.post(
            api_url,
            auth=("api", mailgun_api_key),
            data=data,
            files=files
        )
        sys.stderr.write(f"[Mailgun] Response status: {response.status_code}\n")
        sys.stderr.write(f"[Mailgun] Response text: {response.text}\n")
        response.raise_for_status()  # Raises an HTTPError for bad responses
        sys.stderr.write(f"[Mailgun] Email sent successfully to {to_email}.\n")
        return True
    except requests.exceptions.RequestException as e:
        sys.stderr.write(f"[Mailgun] Failed to send email to {to_email}: {e}\n")
        if 'response' in locals():
            sys.stderr.write(f"[Mailgun] Error response status: {response.status_code}\n")
            sys.stderr.write(f"[Mailgun] Error response text: {response.text}\n")
        return False


def send_receipt_with_ics(to_email, customer_name, shifts_data, ics_content):
    """
    Send a receipt email with ICS attachment and calendar import buttons.
    
    Args:
        to_email (str): Customer's email address
        customer_name (str): Customer's name
        shifts_data (list): List of shift dictionaries with date, start_time, end_time
        ics_content (bytes): ICS file content as bytes
    
    Returns:
        bool: True if email sent successfully
    """
    import sys
    from urllib.parse import quote
    from datetime import datetime
    
    # Generate timestamped filename first
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"work_schedule_{timestamp}.ics"
    
    # Create calendar import URLs
    # Google Calendar - use mobile web version that bypasses app
    google_url = "https://calendar.google.com/calendar/gp#~calendar"
    
    # Outlook
    outlook_url = "https://outlook.live.com/calendar/0/deeplink/compose"
    
    subject = "Your Work Schedule - Calendar Import Ready"    # HTML email template matching myschedule.cloud design
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Your Work Schedule</title>
    </head>
    <body style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #374151; margin: 0; padding: 0; background-color: #f9fafb;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); overflow: hidden;">
            
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%); padding: 32px 24px; text-align: center;">



                <h1 style="color: white; margin: 0; font-size: 24px; font-weight: 600;">

                Hello {customer_name},</p>

                <p style="font-size: 16px; margin: 0 0 24px 0;">
                Thank you for using myschedule.cloud! Your work schedule has been successfully processed and is attached to this email as an .ics calendar file.

                </p>
                <p style="font-size: 16px; margin: 0 0 24px 0;">
                Time to import the .ics file into your calendar program to finish the job.  
                </p>
                <p style="font-size: 16px; margin: 0 0 24px 0;">
                Below are sections on installing .ics files to each popular calendar program and any other email or calendar program out there that supports .ics files.
                </p>
                <p style="font-size: 16px; margin: 0 0 24px 0;">
                The <strong>first step</strong> is to save your .ics file to your device's Downloads folder.
                </p>
            </div>
                
                <!-- Calendar Import Sections -->
                <div style="margin: 32px 0;">
                    <h3 style="font-size: 18px; font-weight: 600; color: #1f2937; margin: 0 0 20px 0; text-align: center;">Choose Your Calendar Progrm</h3>
                    
                    <!-- iPhone/Mac Section -->
                    <details style="margin: 16px 0; border: 1px solid #e5e7eb; border-radius: 8px; background: #f9fafb;">
                        <summary style="padding: 16px; cursor: pointer; font-weight: 600; color: #1f2937; font-size: 16px;">
                            📱 iPhone/Mac Calendar - Click to expand
                        </summary>
                        <div style="padding: 0 16px 16px 16px; color: #374151;">
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 1:</strong> Tap the attached .ics file in this email</p>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 2:</strong> Choose "Add to Calendar" or "Import"</p>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 3:</strong> Select which calendar to add it to</p>
                            <p style="margin: 8px 0; font-size: 12px; color: #6b7280;">✅ Works directly with iPhone Calendar and Mac Calendar apps</p>
                        </div>
                    </details>
                    
                    <!-- Google Calendar Section -->
                    <details style="margin: 16px 0; border: 1px solid #e5e7eb; border-radius: 8px; background: #f9fafb;">
                        <summary style="padding: 16px; cursor: pointer; font-weight: 600; color: #1f2937; font-size: 16px;">
                            📅 Google Calendar - Click to expand
                        </summary>
                        <div style="padding: 0 16px 16px 16px; color: #374151;">
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 1:</strong> Open Google Calendar in browser</p>
                            <div style="margin: 12px 0; text-align: center;">
                                <a href="https://calendar.google.com/calendar/gp#~calendar" style="display: inline-block; background-color: #0ea5e9; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 500; font-size: 14px;">Open Google Calendar</a>
                            </div>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 2:</strong> At the bottom of the screen hit <strong>Desktop</strong></p>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 3:</strong> Gear icon ⚙️ → <strong>Settings</strong></p>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 4:</strong> Scroll down to <strong>Import & Export</strong></p>
                            
                            <div style="margin: 12px 0; padding: 12px; background-color: #f0f9ff; border-radius: 6px; border-left: 3px solid #0ea5e9;">
                                <p style="margin: 0 0 8px 0; font-size: 13px; font-weight: 600; color: #0c4a6e;">📅 Don't have a "myschedule.cloud" calendar?</p>
                                <p style="margin: 0; font-size: 13px; color: #0c4a6e;">Create one first: In the desktop calendar, click "+ Create a calendar" on the left sidebar, name it "myschedule.cloud"</p>
                            </div>
                            
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 5:</strong> Under Import select the .ics file</p>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 6:</strong> Add to calendar: <strong>myschedule.cloud</strong></p>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 7:</strong> Hit <strong>IMPORT</strong> button</p>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Step 8:</strong> You should see a bubble that reads <strong>"Imported 10 out of 10 Events"</strong> (or some other numbers)</p>
                            <p style="margin: 8px 0; font-size: 14px; color: #059669; font-weight: 600;"><strong>Step 9:</strong> Done! ✅</p>
                            <p style="margin: 8px 0; font-size: 12px; color: #6b7280;">💡 Must use web browser, not Google Calendar app on mobile</p>
                        </div>
                    </details>
                    
                    <!-- Outlook Section -->
                    <details style="margin: 16px 0; border: 1px solid #e5e7eb; border-radius: 8px; background: #f9fafb;">
                        <summary style="padding: 16px; cursor: pointer; font-weight: 600; color: #1f2937; font-size: 16px;">
                            📧 Outlook Calendar - Click to expand
                        </summary>
                        <div style="padding: 0 16px 16px 16px; color: #374151;">
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Desktop:</strong> File → Open & Export → Import/Export</p>
                            <p style="margin: 8px 0; font-size: 14px;"><strong>Web/Mobile:</strong> Open Outlook Calendar in browser</p>
                            <div style="margin: 12px 0; text-align: center;">
                                <a href="{outlook_url}" style="display: inline-block; background-color: #0ea5e9; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-size: 13px;">Open Outlook Calendar</a>
                            </div>
                            <p style="margin: 8px 0; font-size: 14px;">Then: Settings → Import Calendar → Choose .ics file</p>
                            <p style="margin: 8px 0; font-size: 12px; color: #6b7280;">✅ Works with Outlook.com, Outlook app, and desktop Outlook</p>
                        </div>
                    </details>
                    
                    <p style="font-size: 14px; color: #6b7280; margin: 20px 0 0 0; text-align: center;">
                        <strong>💡 Tip:</strong> Click any section above for detailed step-by-step instructions
                    </p>
                </div>
                
                <!-- No Cloud Calendar Help -->
                <div style="margin: 32px 0; padding: 20px; background-color: #f0f9ff; border-radius: 8px; border-left: 4px solid #0ea5e9;">
                    <h4 style="font-size: 16px; font-weight: 600; color: #1f2937; margin: 0 0 8px 0;">Don't have a cloud calendar?</h4>
                    <p style="font-size: 14px; color: #374151; margin: 0 0 8px 0;">
                        No problem! You can still use the attached .ics file with:
                    </p>
                    <ul style="font-size: 14px; color: #374151; margin: 0; padding-left: 20px;">
                        <li>Your phone's built-in calendar app (iPhone Calendar, Android Calendar)</li>
                        <li>Desktop calendar programs (Outlook, Thunderbird, Apple Calendar)</li>
                        <li>Any calendar app that accepts .ics files</li>
                    </ul>
                    <p style="font-size: 14px; color: #6b7280; margin: 8px 0 0 0;">
                        Simply open the attached file and your device will ask which calendar to add it to. Then ofcourse, maybe it's time to get a calendar in the cloud.  We recomend Google Calendar.  Its free and easy.
                    </p>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="padding: 24px; background-color: #f9fafb; border-top: 1px solid #e5e7eb; text-align: center;">
                <p style="font-size: 12px; color: #6b7280; margin: 0;">
                    © 2025 myschedule.cloud - Making scheduling simple
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Plain text version
    text_content = f"""Hello {customer_name},

Thank you for using myschedule.cloud! Your work schedule has been successfully processed and is attached as a calendar file.

 Download the attached {filename} file to your Downloads folder.

CHOOSE YOUR CALENDAR PROGRAM FOR INSTALLATION INSTRUCTIONS:

iPhone/Mac: Open the attached .ics file
Google Calendar: Use browser (not app) → calendar.google.com → Settings → Import & Export  
Outlook: File > Open & Export > Import/Export

DON'T HAVE A CLOUD CALENDAR?
No problem! The attached .ics file works with:
- Your phone's built-in calendar app
- Desktop calendar programs (Outlook, Thunderbird, Apple Calendar)  
- Any calendar app that accepts .ics files

Simply open the attached file and your device will ask which calendar to add it to.

Maybe its time to move to the cloud.  Google Calendar is a good choice.

Best regards,
myschedule.cloud Team
"""
    
    # Send email with ICS attachment
    return send_simple_message(
        to_email=to_email,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
        attachment_bytes=ics_content,
        attachment_filename=filename
    )


def test_email_locally():
    """
    Test function to send email locally without going through Cloud Run
    """
    # Sample test data
    test_shifts = [
        {'shift_date': 'Mon, Oct 07', 'shift_start': '9:00 AM', 'shift_end': '5:00 PM', 'department': '026', 'store_number': '#0660'},
        {'shift_date': 'Tue, Oct 08', 'shift_start': '10:00 AM', 'shift_end': '6:00 PM', 'department': '026', 'store_number': '#0660'},
        {'shift_date': 'Wed, Oct 09', 'shift_start': '8:00 AM', 'shift_end': '4:00 PM', 'department': '026', 'store_number': '#0660'}
    ]
    
    # Simple test ICS content
    test_ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//myschedule.cloud//Schedule Generator//EN
METHOD:PUBLISH
X-WR-CALNAME:Test Schedule
BEGIN:VEVENT
SUMMARY:Test Work Shift
DTSTART:20251007T090000
DTEND:20251007T170000
DESCRIPTION:Test shift for email
UID:test-123@myschedule.cloud
END:VEVENT
END:VCALENDAR"""
    
    # Send test email
    success = send_receipt_with_ics(
        to_email="martin.baer@kikis.io",  # Change this to your test email
        customer_name="Test User",
        shifts_data=test_shifts,
        ics_content=test_ics.encode('utf-8')
    )
    
    print(f"Test email sent: {success}")
    return success


if __name__ == "__main__":
    # Run test when script is executed directly
    test_email_locally()

