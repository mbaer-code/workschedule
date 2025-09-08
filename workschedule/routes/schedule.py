# Stripe webhook endpoint to handle payment success
from flask import request, abort
import os
import datetime
import json
import stripe
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from src.services.documentai_processor import process_pdf_documentai_from_bytes
from workschedule.services.stripe_service import create_checkout_session

# Create a Blueprint for schedule-related routes
schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule',
                        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))

# Stripe webhook endpoint to handle payment success

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

# ...existing code...

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
import os
import datetime
import json
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from src.services.documentai_processor import process_pdf_documentai_from_bytes
from workschedule.services.stripe_service import create_checkout_session

# Create a Blueprint for schedule-related routes
schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule',
                        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))

@schedule_bp.route('/approve_schedule', methods=['POST'])
@schedule_bp.route('/approve_schedule', methods=['POST'])
def approve_schedule():
    # For now, re-parse the schedule from the last upload (could use session or persistent storage)
    # You may want to store the parsed schedule in the session for a real flow
    # Here, we just use the last parsed schedule from the upload_pdf route
    # This is a placeholder for demonstration
    # You can pass the parsed_schedule as a hidden field in the form if needed
    # For now, redirect to Stripe payment page
    stripe_session = create_checkout_session(amount=499, currency='usd', description='Schedule ICS File')
    return redirect(stripe_session.url)
# schedule.py

import os
import datetime
import json
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from src.services.documentai_processor import process_pdf_documentai_from_bytes
from workschedule.services.stripe_service import create_checkout_session

# Create a Blueprint for schedule-related routes
schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule',
                        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))

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

@schedule_bp.route("/upload_schedule_new", methods=["GET"])
def upload_schedule_new():
    """Renders the upload schedule page."""
    return render_template("upload_schedule_new.html")

@schedule_bp.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    """
    Handles the PDF upload, processes it, and displays the schedule on the webpage.
    """
    if 'pdfFile' not in request.files:
        return redirect(url_for('schedule_bp.upload_schedule_new'))

    pdf_file = request.files['pdfFile']
    email = request.form.get('email')
    timezone = request.form.get('timezone')

    if not all([pdf_file, email, timezone]):
        return redirect(url_for('schedule_bp.upload_schedule_new'))

    if pdf_file.filename == '':
        return redirect(url_for('schedule_bp.upload_schedule_new'))

    if not pdf_file.filename.lower().endswith('.pdf'):
        return redirect(url_for('schedule_bp.upload_schedule_new'))
    
    try:
        pdf_contents = pdf_file.read()
    except Exception as e:
        print(f"Error reading file contents: {e}")
        return redirect(url_for('schedule_bp.upload_schedule_new'))
    
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
            
        # The key for store number is changed here to 'store' instead of 'store_number'
        for entry in final_output:
            if 'store_number' in entry:
                entry['store'] = entry.pop('store_number')

        # Prepare data for the HTML template
        entities_as_dicts = [entity_to_dict(entity) for entity in entities]
        formatted_json = json.dumps(entities_as_dicts, indent=4)

        # Return the parsed data to the HTML template for display
        return render_template(
            'review_schedule.html',
            parsed_schedule=final_output,
            formatted_json=formatted_json
        )

    except Exception as e:
        print(f"An error occurred during parsing: {e}")
        error_message = f"An error occurred: {e}"
        return render_template("review_schedule.html", raw_json=error_message)

@schedule_bp.route('/download/<job_id>', methods=['GET'])
def download_file(job_id):
    """Placeholder for file download."""
    return render_template('download_page.html', job_id=job_id)

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
