import os
import uuid
import requests
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from werkzeug.utils import secure_filename
from google.cloud import storage, documentai_v1 as documentai
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

    filename = secure_filename(f"{uuid.uuid4()}_{pdf_file.filename}")
    
    # Save PDF to GCS
    gcs_bucket_name = os.getenv("GCS_BUCKET_NAME", "work-schedule-cloud")
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(gcs_bucket_name)
        blob = bucket.blob(filename)
        pdf_file.seek(0)
        blob.upload_from_file(pdf_file, content_type='application/pdf')
        print(f"File {filename} uploaded to GCS.")
    except Exception as e:
        print(f"Error uploading file to GCS: {e}")
        return redirect(url_for('schedule_bp.upload_schedule_new'))

    # Call Document AI
    project_id = os.getenv("DOCUMENT_AI_PROJECT", "fe0baaa28beedbe")
    location = os.getenv("DOCUMENT_AI_LOCATION", "us")
    processor_id = os.getenv("DOCUMENT_AI_PROCESSOR_ID", "fe0baaa28beedbe9")
    gcs_input_uri = f"gs://{gcs_bucket_name}/{filename}"

    docai_client = documentai.DocumentProcessorServiceClient()
    docai_request = {
        "name": f"projects/{project_id}/locations/{location}/processors/{processor_id}",
        "input_documents": {
            "gcs_documents": {
                "documents": [
                    {
                        "gcs_uri": gcs_input_uri,
                        "mime_type": "application/pdf"
                    }
                ]
            }
        }
    }
    try:
        result = docai_client.process_document(request=docai_request)
        entities = [entity for entity in result.document.entities]
        # You may want to use your custom parsing logic here
        # For now, just convert entities to dicts
        parsed_entities = [documentai.types.Entity.to_dict(entity) for entity in entities]
        # Save or display the JSON schedule
        return render_template("review_schedule.html", schedule_json=parsed_entities)
    except Exception as e:
        print(f"Error processing PDF with Document AI: {e}")
        return redirect(url_for('schedule_bp.upload_schedule_new'))

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

