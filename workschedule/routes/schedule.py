# schedule.py

import os
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from src.services.documentai_processor import process_pdf_documentai_from_bytes
from workschedule.services.stripe_service import create_checkout_session
import os
from werkzeug.utils import secure_filename
from src.services.documentai_processor import process_pdf_documentai_from_bytes
# ... other imports

schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule',
                        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))

@schedule_bp.route("/upload_schedule_new", methods=["GET"])
def upload_schedule_new():
    """Renders the upload schedule page."""
    return render_template("upload_schedule_new.html")

@schedule_bp.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    import json
    """
    Handles the PDF upload, processes it in memory, and generates a calendar file.
    """
    # Use Flask's request object directly, do not shadow it
    if 'pdfFile' not in request.files:
        print("Missing fields in form submission: pdfFile")
        return redirect(url_for('schedule_bp.upload_schedule_new'))

    pdf_file = request.files['pdfFile']
    email = request.form.get('email')
    timezone = request.form.get('timezone')

    if not all([pdf_file, email, timezone]):
        print("Missing fields in form submission")
        return redirect(url_for('schedule_bp.upload_schedule_new'))

    if pdf_file.filename == '':
        print("No selected file")
        return redirect(url_for('schedule_bp.upload_schedule_new'))

    # Check if the file is a PDF
    if not pdf_file.filename.lower().endswith('.pdf'):
        print("Invalid file type. Please upload a PDF.")
        return redirect(url_for('schedule_bp.upload_schedule_new'))
    
    # Read the file's content into memory. This is safe for a 22 KB file.
    try:
        pdf_contents = pdf_file.read()
    except Exception as e:
        print(f"Error reading file contents: {e}")
        return redirect(url_for('schedule_bp.upload_schedule_new'))
    
    # Call the new processor function that works on bytes
    try:
        extracted_text, entities = process_pdf_documentai_from_bytes(pdf_contents)

        # Build structured schedule grouped by work shift
        schedule = []
        current_shift = {}
        debug_log_path = os.path.join('instance', 'documentai_debug.log')
        with open(debug_log_path, 'a', encoding='utf-8') as f:
            if entities:
                for ent in entities:
                    entity_type = getattr(ent, 'type_', '').lower() if hasattr(ent, 'type_') else str(ent)
                    value = getattr(ent, 'mention_text', '') if hasattr(ent, 'mention_text') else str(ent)
                    f.write(f"Entity type: {entity_type}, value: {value}\n")
                    if entity_type == 'work-shift':
                        if current_shift:
                            schedule.append(current_shift)
                        current_shift = {'work_shift': value}
                    elif entity_type in [
                        'department', 'meal-end', 'meal-start', 'shift-date',
                        'shift-end', 'start-start', 'store-number'
                    ]:
                        current_shift[entity_type] = value
                if current_shift:
                    schedule.append(current_shift)
                raw_json = json.dumps(schedule, indent=2)
            else:
                raw_json = "No schedule data found or document could not be processed."
        return render_template("review_schedule.html", raw_json=raw_json, parsed_schedule=schedule)
    except Exception as e:
        print(f"Error processing PDF with Document AI: {e}")
        error_message = "No schedule data found or document could not be processed."
        return render_template("review_schedule.html", raw_json=error_message)

@schedule_bp.route('/download/<job_id>', methods=['GET'])
def download_file(job_id):
    # This is a placeholder for a real download function.
    # In a real app, you would generate or retrieve the .ics file here.
    return render_template('download_page.html', job_id=job_id)

@schedule_bp.route('/create-checkout-session', methods=['POST'])
def create_session():
    # Placeholder for the Stripe price ID
    price_id = os.getenv("STRIPE_PRICE_ID")

    # The customer's email would be passed from the front end.
    # For this example, we use a placeholder.
    customer_email = "test.user@example.com"

    session = create_checkout_session(price_id, customer_email)

    if session:
        return jsonify({'id': session.id})
    else:
        return jsonify({'error': 'Failed to create checkout session'}), 500
