from flask import request, abort
import os
import datetime
import json
from flask import session
import stripe
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from src.services.documentai_processor import process_pdf_documentai_from_bytes
from workschedule.services.stripe_service import create_checkout_session

 # Create a Blueprint for schedule-related routes
schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule',
                        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))

BASE_URL= os.getenv("BASE_URL")

# Export to Calendar route
@schedule_bp.route('/export_calendar', methods=['POST'])
def export_calendar():
    from workschedule.services.ics_generator import extract_shifts_from_docai_entities, create_ics_from_entries
    from workschedule.services.mailgun_service import send_simple_message
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

    # Fetch schedule from DB
    from workschedule.models import Schedule
    import json
    schedule_entry = Schedule.query.filter_by(job_id=job_id).first()
    if not schedule_entry:
        error_message = "No schedule found for this job_id. Cannot proceed to payment."
        print(f"[DEBUG] ERROR: {error_message}")
        return render_template("review_schedule.html", parsed_schedule=[], raw_json=error_message)
    parsed_schedule = json.loads(schedule_entry.schedule_data)
    print(f"[DEBUG] Loaded schedule from DB for job_id={job_id}: {parsed_schedule}")

    # If parsed_schedule is empty, try to get it from the form and persist it
    if not parsed_schedule and request.form.get('parsed_schedule'):
        try:
            new_schedule = json.loads(request.form.get('parsed_schedule'))
            print(f"[DEBUG] approve_schedule: Persisting new schedule for job_id={job_id}: {new_schedule}")
            schedule_entry.schedule_data = json.dumps(new_schedule)
            from workschedule.app import db
            db.session.commit()
            parsed_schedule = new_schedule
        except Exception as e:
            print(f"[DEBUG] approve_schedule: Failed to persist new schedule: {e}")

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
    customer_email = schedule_entry.user_email or "test.user@example.com"
    stripe_session = create_checkout_session(
        price_id,
        customer_email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'job_id': job_id}
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

 # ...existing code...

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
        extracted_text, entities = process_pdf_documentai_from_bytes(pdf_contents)

        if not entities:
            error_message = "No schedule data found or document could not be processed."
            return render_template("review_schedule.html", parsed_schedule=[], raw_json=error_message)

        # 1. Extract only valid work shifts
        parsed_shifts = []
        for entity in entities:
            if entity.type_ == "Work-shift":
                properties = {prop.type_: prop.mention_text.strip() for prop in entity.properties}
                
                # Check for core properties to ensure it's a complete shift
                if all(field in properties for field in ['Shift-date', 'Shift-end', 'Start-start', 'Department', 'Store-number']):
                    
                    shift_date_raw = properties.get('Shift-date', '')
                    
                    try:
                        date_str = shift_date_raw.replace('\n', ' ').strip()
                        parsed_date = datetime.datetime.strptime(date_str, '%b %d').date().replace(year=datetime.date.today().year)
                        
                        # Get the department value and remove "Associate" if it exists
                        department_name = properties.get('Department', '')
                        if department_name.endswith(' Associate'):
                            department_name = department_name[:-len(' Associate')]
                        
                        parsed_shifts.append({
                            'shift_date': parsed_date,
                            'department': department_name,
                            'shift_start': properties.get('Start-start'),
                            'shift_end': properties.get('Shift-end'),
                            'store_number': properties.get('Store-number')
                        })
                    except ValueError:
                        continue # Silently ignore shifts with unparsable dates

        # 2. Sort the list of shifts chronologically
        parsed_shifts.sort(key=lambda x: x['shift_date'])

        # 3. Format the dates and prepare the final list for the template
        final_output = []
        for shift in parsed_shifts:
            shift_date = shift.pop('shift_date')
            final_output.append({
                'shift_date': shift_date.strftime('%a, %b %d'),
                **shift
            })
            
    # Keep the key as 'store_number' for consistency with template

        # Prepare data for the HTML template
        entities_as_dicts = [entity_to_dict(entity) for entity in entities]
        formatted_json = json.dumps(entities_as_dicts, indent=4)


        # Persist parsed schedule to database
        import uuid
        from workschedule.models import Schedule
        from workschedule.app import db
        job_id = str(uuid.uuid4())
        # Save as JSON string
        schedule_json = json.dumps(final_output)
        schedule_entry = Schedule(
            user_email=email,
            job_id=job_id,
            schedule_data=schedule_json
        )
        db.session.add(schedule_entry)
        db.session.commit()

        # Store job_id in session for use in approval and export
        session['job_id'] = job_id

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
    # 1. Verify payment (optional, recommended)
    session_id = request.args.get('session_id')
    payment_verified = False
    if session_id:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            if checkout_session.payment_status == 'paid':
                payment_verified = True
        except Exception as e:
            return render_template('payment_success.html', message=f"Error verifying payment: {e}")

    if not payment_verified and session_id:
        return render_template('payment_success.html', message="Payment not verified.")

    # 2. Retrieve job_id from session or Stripe metadata
    job_id = request.args.get('job_id') or session.get('job_id')
    print(f"[payment_success] job_id from request.args: {request.args.get('job_id')}")
    print(f"[payment_success] job_id from session: {job_id}")
    if not job_id and session_id:
        try:
            job_id = checkout_session.metadata.get('job_id')
            print(f"[payment_success] job_id from Stripe metadata: {job_id}")
        except Exception as e:
            print(f"[payment_success] ERROR retrieving job_id from Stripe metadata: {e}")
            job_id = None
    if not job_id:
        print(f"[payment_success] ERROR: No job_id found. Cannot retrieve schedule.")
        return render_template('payment_success.html', message="No job_id found. Cannot retrieve schedule.")

    # 3. Fetch schedule from database
    from workschedule.models import Schedule
    schedule_entry = Schedule.query.filter_by(job_id=job_id).first()
    if not schedule_entry:
        return render_template('payment_success.html', message="No schedule found for this job_id.")
    import json
    parsed_schedule = json.loads(schedule_entry.schedule_data)

    # 4. Generate ICS file
    from workschedule.services.ics_generator import extract_shifts_from_docai_entities, create_ics_from_entries
    shift_entries = extract_shifts_from_docai_entities(parsed_schedule)
    calendar_name = "myschedule.cloud"
    ics_content = create_ics_from_entries(shift_entries, calendar_name=calendar_name)

    # 5. Send email
    from workschedule.services.mailgun_service import send_simple_message
    email = session.get('user_email')
    if not email and session_id:
        try:
            email = checkout_session.customer_email
        except Exception:
            email = None
    if not email:
        return render_template('payment_success.html', message="No email found for user.")

    # Use http for localhost, https for cloud
    #if request.host.startswith("127.0.0.1") or request.host.startswith("localhost"):
    #    download_url = f"http://{request.host}/schedule/download/{job_id}"
    #else:
    #    download_url = f"https://{request.host/schedule/download/{job_id}"}
    download_url = f"{BASE_URL}/schedule/download/{job_id}"


    subject = f"Your {calendar_name} Schedule ICS File"
    text_content = (
        "Attached is your work schedule as an ICS file. You can import it into Google Calendar, Apple Calendar, or Outlook.\n\n"
        f"Download your calendar file here: {download_url}"
    )
    html_content = (
        f"<p>Attached is your work schedule as an ICS file. You can import it into Google Calendar, Apple Calendar, or Outlook.</p>"
        f"<p><a href='{download_url}'>Download your calendar file</a></p>"
    )
    send_success = send_simple_message(
        to_email=email,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
        attachment_bytes=ics_content.encode('utf-8'),
        attachment_filename=f"{calendar_name}.ics"
    )

    # 6. Render success page
    if send_success:
        message = f"ICS file sent to {email}. Check your inbox!"
    else:
        message = f"Failed to send ICS file to {email}. Please try again."
    return render_template('payment_success.html', message=message)

@schedule_bp.route('/payment_cancel', methods=['GET'])
def payment_cancel():
    return render_template('payment_cancel.html')
