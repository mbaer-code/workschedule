from flask import request, abort
import os
import datetime
import json
from flask import session
import stripe
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
import re
import fitz  # PyMuPDF for PDF text extraction
from workschedule.services.stripe_service import create_checkout_session
from workschedule.services.mailgun_service import send_simple_message

# Create a Blueprint for schedule-related routes
schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule',
                        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))

BASE_URL= os.getenv("BASE_URL")

# Export to Calendar route
@schedule_bp.route('/export_calendar', methods=['POST'])
def export_calendar():
    from workschedule.services.ics_generator import extract_shifts_from_docai_entities, create_ics_from_entries
    import workschedule.services.ics_delivery
    from flask import make_response, request
    from workschedule.models import Schedule
    job_id_form = request.form.get('job_id')
    job_id_session = session.get('job_id')
    job_id = job_id_form or job_id_session
    print(f"[DEBUG] export_calendar: job_id from form={job_id_form}, job_id from session={job_id_session}, using job_id={job_id}")
    schedule_entry = Schedule.query.filter_by(job_id=job_id).first()
    print(f"[DEBUG] export_calendar: schedule_entry from DB={schedule_entry}")
    print(f"[DEBUG] export_calendar: raw schedule_data from DB={getattr(schedule_entry, 'schedule_data', None)}")
    if not schedule_entry:
        print(f"[DEBUG] export_calendar: No schedule entry found for job_id={job_id}")
        return render_template('review_schedule.html', parsed_schedule=[], raw_json='No schedule data found for this job.')
    import json
    parsed_schedule = json.loads(schedule_entry.schedule_data)
    print(f"[DEBUG] export_calendar: loaded schedule_data={parsed_schedule}")
    if not parsed_schedule:
        print(f"[DEBUG] export_calendar: No schedule data to export for job_id={job_id}")
        return render_template('review_schedule.html', parsed_schedule=[], raw_json='No schedule data to export.')

    print(f"[DEBUG] export_calendar: parsed_schedule type={type(parsed_schedule)} length={len(parsed_schedule) if hasattr(parsed_schedule, '__len__') else 'N/A'}")
    print(f"[DEBUG] export_calendar: passing parsed_schedule directly to ICS generator")
    calendar_name = request.form.get('calendar_name', 'myschedule.cloud')
    timezone = request.form.get('timezone', 'America/Los_Angeles')
    email = request.form.get('email')
    ics_content = create_ics_from_entries(parsed_schedule, calendar_name=calendar_name)
    # If your ICS generator supports time zone, pass it here (update function signature if needed)

    # Store ICS content in DB or persistent storage here (not shown)
    # Generate download link for the ICS file
    job_id = session.get('job_id', 'unknown')
    # Use http for localhost, https for cloud

    #if request.host.startswith("127.0.0.1") or request.host.startswith("localhost"):
    #    download_url = f"http://{request.host}/schedule/download/{job_id}"
    #else:
    #    download_url = f"https://{request.host}/schedule/download/{job_id}"

    download_url = f"{BASE_URL}/schedule/download/{job_id}"

    subject = f"Your {calendar_name} Schedule ICS File"
    text_content = (
        "Your work schedule is ready! You can import it into Google Calendar, Apple Calendar, or Outlook.\n\n"
        f"Download your calendar file here: {download_url}"
    )
    html_content = (
        f"<p>Your work schedule is ready! You can import it into Google Calendar, Apple Calendar, or Outlook.</p>"
        f"<p><a href='{download_url}'>Download your calendar file</a></p>"
    )
    success = send_simple_message(
        to_email=email,
        subject=subject,
        text_content=text_content,
        html_content=html_content
    )

    if success:
        success_message = f"ICS download link sent to {email}. Check your inbox!"
    else:
        success_message = f"Failed to send ICS download link to {email}. Please try again."

    return render_template('review_schedule.html', parsed_schedule=parsed_schedule, raw_json=success_message)

@schedule_bp.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    event = None
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        print(f"Stripe webhook error: {e}")
        return abort(400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        print(f"Stripe webhook signature error: {e}")
        return abort(400)

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get('customer_email')
        # TODO: Generate ICS file and send Mailgun email to customer_email
        print(f"Payment succeeded for {customer_email}. Trigger ICS and email.")

    return '', 200


@schedule_bp.route('/approve_schedule', methods=['POST'])
def approve_schedule():
    # For now, re-parse the schedule from the last upload (could use session or persistent storage)
    # You may want to store the parsed schedule in the session for a real flow
    # Here, we just use the last parsed schedule from the upload_pdf route
    # This is a placeholder for demonstration
    # You can pass the parsed_schedule as a hidden field in the form if needed
    # For now, redirect to Stripe payment page
    # Retrieve parsed schedule from session
    print("[DEBUG] approve_schedule route registered")
    print(f"[DEBUG] request.method: {request.method}")
    print(f"[DEBUG] request.form: {request.form}")
    print(f"[DEBUG] request.args: {request.args}")
    job_id = request.args.get('job_id') or request.form.get('job_id')
    print(f"[DEBUG] Received job_id: {job_id}")
    if not job_id:
        error_message = "No job_id found. Cannot proceed to payment."
        print(f"[DEBUG] ERROR: {error_message}")
        return render_template("review_schedule.html", parsed_schedule=[], raw_json=error_message)

    # Fetch schedule from GCS bucket
    parsed_blob = session.get('parsed_blob') or f"parsed/{job_id}.json"
    bucket_name = os.environ.get('GCS_BUCKET_NAME', 'work-schedule-parsed')
    from google.cloud import storage
    gcs_client = storage.Client()
    bucket = gcs_client.bucket(bucket_name)
    blob = bucket.blob(parsed_blob)
    try:
        schedule_json = blob.download_as_text()
        print(f"[DEBUG] approve_schedule: downloaded from bucket {bucket_name} parsed_blob {parsed_blob}: {schedule_json}")
        parsed_schedule = json.loads(schedule_json)
        print(f"[DEBUG] approve_schedule: parsed_schedule loaded from GCS: {parsed_schedule}")
    except Exception as e:
        error_message = f"Error loading parsed schedule from GCS: {e}"
        print(f"[DEBUG] approve_schedule: {error_message}")
        return render_template("review_schedule.html", parsed_schedule=[], raw_json=error_message)

    # Stripe payment logic
    #success_url = f"http://127.0.0.1:8080/schedule/payment_success?job_id={job_id}" if job_id else "http://127.0.0.1:8080/schedule/payment_success"
    #success_url = f"http://127.0.0.1:8080/schedule/payment_success?job_id={job_id}" 
    #cancel_url = "http://127.0.0.1:8080/schedule/payment_cancel"

    if job_id: 
        success_url = f"{BASE_URL}/schedule/payment_success?job_id={job_id}"
    else:
        success_url = f"{BASE_URL}/schedule/payment_success"

    print(f"[approve_schedule] Stripe success_url: {success_url}")

    cancel_url = f"{BASE_URL}/schedule/payment_cancel"

    price_id = os.getenv("STRIPE_PRICE_ID")
    customer_email = session.get('user_email', "test.user@example.com")
    coupon_code = request.form.get('coupon_code') or request.args.get('coupon_code')
    
    stripe_session = create_checkout_session(
        price_id,
        customer_email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'job_id': job_id},
        coupon_code=coupon_code
    )
    print(f"[approve_schedule] Stripe session metadata: {stripe_session.metadata if hasattr(stripe_session, 'metadata') else 'No metadata'}")
    if not stripe_session or not hasattr(stripe_session, 'url'):
        error_message = "Stripe session could not be created. Please try again later."
        print(f"[approve_schedule] ERROR: {error_message}")
        return render_template("review_schedule.html", parsed_schedule=[], raw_json=error_message)
    print(f"[approve_schedule] Redirecting to Stripe checkout URL: {stripe_session.url}")
    return redirect(stripe_session.url)
# schedule.py

import os
import datetime
import json
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from src.services.documentai_processor import process_pdf_documentai_from_bytes
from workschedule.services.stripe_service import create_checkout_session

# Remove stray top-level code fragments from previous patch attempts
# All logic for GCS bucket upload/download is now inside upload_pdf and approve_schedule

def extract_text_from_pdf(pdf_contents):
    """Extract text from PDF using PyMuPDF."""
    try:
        doc = fitz.open(stream=pdf_contents, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""

def parse_schedule_text(text):
    """Parse schedule text directly without CSV intermediate step."""
    print("=== EXTRACTED TEXT ===")
    print(text[:500] + "..." if len(text) > 500 else text)
    print("=== END EXTRACTED TEXT ===")
    
    results = []
    
    if "not assigned" in text.lower() or "not scheduled" in text.lower():
        return results

    # Find all shift patterns with their associated store/department info
    # Look for: "Sep 22 1:30 PM - 10:00 PM [8:00] 0660 - Store 026 - Plumbing & Bath Associate"
    full_shift_pattern = re.compile(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)\s*\[[\d:]+\]\s*(\d{4})\s*-\s*Store\s+(\d{3})', re.IGNORECASE)
    full_shifts = full_shift_pattern.findall(text)
    
    if full_shifts:
        print(f"Found {len(full_shifts)} shifts with full store/dept info: {full_shifts}")
        for shift in full_shifts:
            month, date, start_time, end_time, dept_code, store_code = shift
            
            results.append({
                'username': '',
                'store_number': f"#{dept_code}",  # e.g., "#0660"
                'weekday': '',
                'month': month,
                'date': date,
                'shift_start': start_time,
                'meal_start': '',
                'meal_end': '',
                'shift_end': end_time,
                'department': store_code  # e.g., "026"
            })
    else:
        # Fallback to simpler pattern if full pattern doesn't match
        shift_pattern = re.compile(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)', re.IGNORECASE)
        shifts = shift_pattern.findall(text)
        
        # Try to extract default store/dept from anywhere in text
        store_match = re.search(r'(\d{4})\s*-\s*Store', text)  # Gets 0660
        dept_match = re.search(r'Store\s+(\d{3})', text)  # Gets 026
        
        default_store = f"#{store_match.group(1)}" if store_match else ''  # #0660
        default_dept = dept_match.group(1) if dept_match else ''  # 026
        
        print(f"Found {len(shifts)} shifts with fallback pattern, using defaults: store={default_store}, dept={default_dept}")
        
        for shift in shifts:
            month, date, start_time, end_time = shift
            
            results.append({
                'username': '',
                'store_number': default_store,
                'weekday': '',
                'month': month,
                'date': date,
                'shift_start': start_time,
                'meal_start': '',
                'meal_end': '',
                'shift_end': end_time,
                'department': default_dept
            })
    
    print(f"Parsed {len(results)} total shifts")
    return results

def entity_to_dict(entity):
    """Recursively converts a Document AI entity to a dictionary."""
    entity_dict = {
        'type_': entity.type_,
        'mention_text': entity.mention_text,
        'confidence': entity.confidence,
        'page_anchor': entity.page_anchor.page_refs[0].page if entity.page_anchor.page_refs else None,
        'properties': []
    }
    if entity.properties:
        for prop in entity.properties:
            entity_dict['properties'].append(entity_to_dict(prop))
    return entity_dict


@schedule_bp.route("/upload", methods=["GET"])
def upload_schedule():
    """Renders the upload schedule page."""
    return render_template("upload_schedule_new.html")

@schedule_bp.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    """
    Handles the PDF upload, processes it, and displays the schedule on the webpage.
    """
    if 'pdfFile' not in request.files:
        return redirect(url_for('schedule_bp.upload_schedule'))

    pdf_file = request.files['pdfFile']
    email = request.form.get('email')
    timezone = request.form.get('timezone')


    if not email:
        error_message = "Email address is required."
        return render_template("upload_schedule_new.html", email_error=error_message)
    if not timezone:
        error_message = "Time zone is required."
        return render_template("upload_schedule_new.html", timezone_error=error_message)
    if not pdf_file:
        error_message = "PDF file is required."
        return render_template("upload_schedule_new.html", pdf_error=error_message)

    # Store email and timezone in session for later use in payment flow and ICS generation
    session['user_email'] = email
    session['timezone'] = timezone

    if pdf_file.filename == '':
        return redirect(url_for('schedule_bp.upload_schedule'))

    if not pdf_file.filename.lower().endswith('.pdf'):
        return redirect(url_for('schedule_bp.upload_schedule'))
    
    try:
        pdf_contents = pdf_file.read()
    except Exception as e:
        print(f"Error reading file contents: {e}")
        return redirect(url_for('schedule_bp.upload_schedule'))
    
    try:
        # Extract text from PDF
        extracted_text = extract_text_from_pdf(pdf_contents)
        
        if not extracted_text or len(extracted_text.strip()) < 50:
            error_message = "No schedule data found or document could not be processed."
            return render_template("review_schedule.html", parsed_schedule=[], raw_json=error_message)

        # Parse text directly without CSV intermediate step
        parsed_entries = parse_schedule_text(extracted_text)
        
        if not parsed_entries:
            error_message = "No valid schedule entries found in the document."
            return render_template("review_schedule.html", parsed_schedule=[], raw_json=error_message)

        # Convert parser output to template format
        parsed_shifts = []
        for entry in parsed_entries:
            try:
                # Combine month and date to create a proper date
                year = datetime.date.today().year
                month = datetime.datetime.strptime(entry['month'], "%b").month
                day = int(entry['date'])
                shift_date = datetime.date(year, month, day)
                
                # Clean up department name
                department_name = entry.get('department', '')
                if department_name.endswith(' Associate'):
                    department_name = department_name[:-len(' Associate')]
                
                parsed_shifts.append({
                    'shift_date': shift_date,
                    'department': department_name,
                    'shift_start': entry.get('shift_start', ''),
                    'shift_end': entry.get('shift_end', ''),
                    'store_number': entry.get('store_number', '')
                })
            except (ValueError, KeyError) as e:
                print(f"Skipping invalid entry: {entry}, Error: {e}")
                continue

        # Sort chronologically
        parsed_shifts.sort(key=lambda x: x['shift_date'])

        # Format dates for template
        final_output = []
        for shift in parsed_shifts:
            shift_date = shift.pop('shift_date')
            final_output.append({
                'shift_date': shift_date.strftime('%a, %b %d'),
                **shift
            })
            
    # Keep the key as 'store_number' for consistency with template

        # Prepare data for the HTML template  
        formatted_json = json.dumps(parsed_entries, indent=4)

        # Persist parsed schedule to GCS bucket
        import uuid
        job_id = str(uuid.uuid4())
        schedule_json = json.dumps(final_output)
        bucket_name = os.environ.get('GCS_BUCKET_NAME', 'work-schedule-parsed')
        from google.cloud import storage
        gcs_client = storage.Client()
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(f"parsed/{job_id}.json")
        print(f"[DEBUG] upload_pdf: uploading to bucket {bucket_name} as parsed/{job_id}.json: {schedule_json}")
        blob.upload_from_string(schedule_json, content_type='application/json')
        print(f"[DEBUG] upload_pdf: uploaded parsed schedule to GCS as parsed/{job_id}.json")

        session['job_id'] = job_id
        session['parsed_blob'] = f"parsed/{job_id}.json"

        # Pass job_id to template for later use
        return render_template(
            'review_schedule.html',
            parsed_schedule=final_output,
            formatted_json=formatted_json,
            job_id=job_id
        )

    except Exception as e:
        print(f"An error occurred during parsing: {e}")
        error_message = f"An error occurred: {e}"
        # Try to pass job_id if it exists in local or session
        job_id = locals().get('job_id') or session.get('job_id')
        return render_template("review_schedule.html", raw_json=error_message, job_id=job_id)

@schedule_bp.route('/download/<job_id>', methods=['GET'])
def download_file(job_id):
    # Serve the ICS file for the given job_id
    from workschedule.models import Schedule
    from workschedule.services.ics_generator import create_ics_from_entries
    import json
    schedule_entry = Schedule.query.filter_by(job_id=job_id).first()
    if not schedule_entry:
        return "No schedule found for this job_id.", 404
    parsed_schedule = json.loads(schedule_entry.schedule_data)
    calendar_name = "myschedule.cloud"
    ics_content = create_ics_from_entries(parsed_schedule, calendar_name=calendar_name)
    from flask import Response
    response = Response(ics_content, mimetype="text/calendar")
    response.headers["Content-Disposition"] = f"attachment; filename={calendar_name}.ics"
    return response

@schedule_bp.route('/create-checkout-session', methods=['POST'])
def create_session():
    """Placeholder for Stripe checkout session creation."""
    price_id = os.getenv("STRIPE_PRICE_ID")
    customer_email = "test.user@example.com"
    session = create_checkout_session(price_id, customer_email)

    if session:
        return jsonify({'id': session.id})
    else:
        return jsonify({'error': 'Failed to create checkout session'}), 500

# Stripe payment success and cancel endpoints
@schedule_bp.route('/payment_success', methods=['GET'])

@schedule_bp.route('/payment_success', methods=['GET'])
def payment_success():
    # Defensive: Assign job_id, schedule_entry, and parsed_schedule before error checks
    job_id = request.args.get('job_id')
    parsed_blob = f"parsed/{job_id}.json"
    bucket_name = os.environ.get('GCS_BUCKET_NAME', 'work-schedule-parsed')
    from google.cloud import storage
    gcs_client = storage.Client()
    bucket = gcs_client.bucket(bucket_name)
    blob = bucket.blob(parsed_blob)
    try:
        schedule_json = blob.download_as_text()
        print(f"[DEBUG] payment_success: downloaded from bucket {bucket_name} parsed_blob {parsed_blob}: {schedule_json}")
        parsed_schedule = json.loads(schedule_json)
        print(f"[DEBUG] payment_success: parsed_schedule loaded from GCS: {parsed_schedule}")
    except Exception as e:
        return jsonify({"error": f"Error loading schedule from GCS: {e}"}), 404
    # 1. Verify payment (optional, recommended)
    session_id = request.args.get('session_id')
    payment_verified = False
    if session_id:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        # --- NEW LOGIC ---

    # Generate ICS content and deliver via GCS
    from workschedule.services.ics_generator import create_ics_from_entries
    from workschedule.services.ics_delivery import deliver_ics_file
    calendar_name = "myschedule.cloud"
    ics_content = create_ics_from_entries(parsed_schedule, calendar_name=calendar_name)
    magic_link = deliver_ics_file(ics_content)
    return render_template(
        'payment_success.html',
        ics_link=magic_link,
        message="Payment successful. Your schedule is ready.",
        success=True
    )

@schedule_bp.route('/payment_cancel', methods=['GET'])
def payment_cancel():
    return render_template('payment_cancel.html')
