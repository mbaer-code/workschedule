import os
import uuid
import requests
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from werkzeug.utils import secure_filename
from google.cloud import storage
from datetime import datetime
from workschedule.services.mailgun_service import send_simple_message
from workschedule.services.calendar_service import generate_ics_file
from workschedule.services.stripe_service import create_checkout_session

schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule',
                        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))

@schedule_bp.route("/upload_schedule_new", methods=["GET"])
def upload_schedule_new():
    """Renders the upload schedule page."""
    return render_template("upload_schedule_new.html")

@schedule_bp.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    """
    Handles the PDF upload, processes it, and generates a calendar file.
    """
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

    filename = secure_filename(f"{uuid.uuid4()}_{pdf_file.filename}")
    
    # Placeholder for PDF processing and calendar generation
    job_id = "test-job-123"
    
    if current_app.config.get("GCS_BUCKET"):
        try:
            client = storage.Client()
            bucket = client.bucket(current_app.config.get("GCS_BUCKET"))
            blob = bucket.blob(filename)
            blob.upload_from_file(pdf_file, content_type='application/pdf')
            print(f"File {filename} uploaded to GCS.")
        except Exception as e:
            print(f"Error uploading file to GCS: {e}")
            return redirect(url_for('schedule_bp.upload_schedule_new'))

    # If the user has a premium subscription, send the .ics file via email
    # Placeholder for subscription logic
    is_premium_user = False
    
    if is_premium_user:
        # Placeholder for real schedule data
        work_schedule = {
            'events': [
                {
                    'start_time': datetime.now(),
                    'end_time': datetime.now(),
                    'summary': 'Sample Event'
                }
            ]
        }
        ics_content = generate_ics_file(work_schedule, timezone)
        
        # Send email with .ics attachment
        email_sent = send_simple_message(
            to_email=email,
            subject="Your Work Schedule Calendar",
            text_content="Please find your .ics calendar file attached.",
            # In a real app, you would attach the file here
        )
        if email_sent:
            return render_template("success_page.html")
        else:
            print("Failed to send email.")
            return redirect(url_for('schedule_bp.upload_schedule_new'))
    else:
        # For free users, redirect to a download page
        return redirect(url_for('schedule_bp.download_file', job_id=job_id))

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

