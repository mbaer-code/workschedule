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
    
    # Outlook - main calendar web interface for importing
    outlook_url = "https://outlook.live.com/calendar/"
    
    subject = "Your Work Schedule - Calendar Import Ready"
    
    # HTML email template with improved table-based layout for better email compatibility
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Your Work Schedule</title>
    </head>
    <body style="font-family: 'Inter', Helvetica, Arial, sans-serif; line-height: 1.6; color: #374151; margin: 0; padding: 0; background-color: #f9fafb;">

        <!-- Outer Table (Ensures full-screen width and centering) -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #f9fafb;">
            <tr>
                <td align="center" style="padding: 20px 10px;">

                    <!-- Email Container (Fixed max-width, center content) -->
                    <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; background-color: white; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); overflow: hidden;">
                        
                        <!-- Header -->
                        <tr>
                            <td align="center" style="background-color: #0ea5e9; padding: 16px 24px;">
                                <div style="font-size: 28px; font-weight: bold; color: white;">MySchedule.cloud</div>
                            </td>
                        </tr>
                        
                        <!-- Main Content Area -->
                        <tr>
                            <td style="padding: 24px;">
                                
                                <!-- Introduction -->
                                <h1 style="color: #1f2937; margin: 0 0 20px 0; font-size: 24px; font-weight: 700;">
                                    Hello {customer_name},
                                </h1>

                                <p style="font-size: 16px; margin: 0 0 18px 0;">
                                    Thank you for using MySchedule.cloud! Your work schedule has been successfully processed and is attached to this email as an <strong>.ics calendar file</strong>.
                                </p>
                                <p style="font-size: 16px; margin: 0 0 32px 0;">
                                    Follow the simple steps below to import your schedule into your preferred calendar application.
                                </p>
                                
                                <!-- Calendar Instructions Container - Consolidated Instructions -->
                                <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                    
                                    <!-- ========================================================= -->
                                    <!-- 1. APPLE (SIMPLE INSTRUCTION) -->
                                    <!-- ========================================================= -->
                                    <tr>
                                        <td style="padding-bottom: 25px;">
                                            <div style="background-color: #f1f5f9; padding: 15px 20px; border-radius: 8px;">
                                                <span style="font-weight: 700; font-size: 18px; color: #059669; margin: 0 0 10px 0; display: block;">Apple (iPhone, iPad, Mac Calendar):</span>
                                                
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>1. Tap or Double-Click:</strong> Open the attached <strong>.ics file</strong> in this email or on your device.</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>2. Confirm:</strong> Choose <strong>"Add to Calendar"</strong> or <strong>"Import"</strong> when prompted by the Calendar application.</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>3. Select:</strong> Select the calendar you wish to add the events to.</p>
                                                <p style="font-size: 12px; color: #6b7280; margin-top: 15px;">*This works directly on Apple devices and Mac desktop apps.*</p>
                                            </div>
                                        </td>
                                    </tr>

                                    <!-- ========================================================= -->
                                    <!-- 2. GOOGLE CALENDAR (WEB-FOCUSED STEPS) -->
                                    <!-- ========================================================= -->
                                    <tr>
                                        <td style="padding-bottom: 25px;">
                                            <div style="background-color: #f1f5f9; padding: 15px 20px; border-radius: 8px;">
                                                <span style="font-weight: 700; font-size: 18px; color: #1e40af; margin: 0 0 10px 0; display: block;">Google Calendar (Web):</span>
                                                
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>1. Save File:</strong> Save the attached <strong>.ics file</strong> to your Downloads folder.</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>2. Open Calendar:</strong> Click the button below to go to the Google Calendar website.</p>
                                                
                                                <div style="margin: 15px 0; text-align: center;">
                                                    <a href="{google_url}" target="_blank" style="display: inline-block; background-color: white; color: #0ea5e9; border: 1px solid #0ea5e9; padding: 9px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;">Open Google Calendar Website</a>
                                                </div>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>3. Switch View:</strong> Click the <strong>Desktop</strong> link at the bottom of the page.</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>4. Go to Import:</strong> Click the <strong>Gear icon</strong> → <strong>Settings</strong> → <strong>Import & Export</strong> on the left menu.</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>5. Select Files:</strong> Select the <strong>.ics file</strong> you saved, and choose <strong>MySchedule.cloud</strong> (or your default) from the calendar dropdown.</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>6. Final Import:</strong> Click the blue <strong>Import</strong> button. A bubble should appear reading <strong>"Imported [num] out of [num] Events"</strong> (or similar) when done.</p>
                                                <p style="font-size: 12px; color: #6b7280; margin-top: 15px;">*You must use the Google Calendar website for file importing, even on a phone.*</p>
                                            </div>
                                        </td>
                                    </tr>

                                    <!-- ========================================================= -->
                                    <!-- 3. OUTLOOK (WEB-FOCUSED STEPS - SIMPLIFIED) -->
                                    <!-- ========================================================= -->
                                    <tr>
                                        <td style="padding-bottom: 30px;">
                                            <div style="background-color: #f1f5f9; padding: 15px 20px; border-radius: 8px;">
                                                <span style="font-weight: 700; font-size: 18px; color: #1e40af; margin: 0 0 10px 0; display: block;">Outlook Calendar (Web):</span>

                                                <p style="font-size: 15px; margin: 8px 0;"><strong>1. Save File:</strong> Save the attached <strong>.ics file</strong> to your device.</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>2. Open Calendar:</strong> Click the button below to go to the Outlook Calendar website.</p>
                                                
                                                <div style="margin: 15px 0; text-align: center;">
                                                    <a href="{outlook_url}" target="_blank" style="display: inline-block; background-color: white; color: #0ea5e9; border: 1px solid #0ea5e9; padding: 9px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px;">Open Outlook Calendar Website</a>
                                                </div>

                                                <p style="font-size: 15px; margin: 8px 0;"><strong>3. Go to Import:</strong> In Outlook, click <strong>Add calendar</strong> (on the left menu).</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>4. Upload File:</strong> Select <strong>Upload from file</strong> and choose the <strong>.ics file</strong> you saved.</p>
                                                <p style="font-size: 15px; margin: 8px 0;"><strong>5. Final Import:</strong> Select a calendar (e.g., your primary calendar) and click <strong>Import</strong>.</p>
                                                
                                                <p style="font-size: 12px; color: #6b7280; margin-top: 15px;">*This web method is the best approach for both desktop and mobile users.*</p>
                                            </div>
                                        </td>
                                    </tr>

                                </table>

                                <!-- Alternative/Offline Calendar Help -->
                                <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb;">
                                    <h4 style="font-size: 16px; font-weight: 700; color: #1f2937; margin: 0 0 12px 0;">
                                        Alternative Calendar Support
                                    </h4>
                                    <p style="font-size: 14px; color: #374151; margin: 0 0 12px 0;">
                                        The attached file is a universal <strong>.ics file</strong> and is compatible with virtually all calendar applications (e.g., Thunderbird, eM Client, etc.).
                                    </p>
                                    <p style="font-size: 14px; color: #374151; margin: 0;">
                                        <strong>General Tip:</strong> Simply open or tap the attached <strong>.ics file</strong> and your device will automatically prompt you to add the events to your local calendar.
                                    </p>
                                </div>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td align="center" style="padding: 24px; background-color: #f9fafb; border-top: 1px solid #e5e7eb;">
                                <p style="font-size: 12px; color: #6b7280; margin: 0;">
                                    &copy; 2025 MySchedule.cloud - Making scheduling simple
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
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

