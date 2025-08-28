from flask import send_file, Response
# Temporary storage for last ICS data (for download)
last_ics_data = None
# src/routes/schedule.py
# This file defines the blueprint for schedule-related routes.

import os
import logging
import tempfile
from flask import Blueprint, render_template, request, jsonify
from workschedule.routes.auth import login_required
from werkzeug.utils import secure_filename
from google.cloud import documentai_v1 as documentai

# Create a Blueprint instance
schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule')

@schedule_bp.route('/upload', methods=['GET'])
def upload_form():
    """
    Renders the PDF upload form.
    """
    return render_template('upload.html')




@schedule_bp.route('/upload_pdf', methods=['POST'])
@login_required
def upload_pdf():
    """
    Handles the POST request for a PDF file upload.
    This is the backend logic for Session 5.
    It performs initial validation and a placeholder action.
    The actual Document AI processing will be implemented in a later session.
    """
    import json
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['pdf_file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and file.filename.endswith('.pdf'):
        try:
            filename = secure_filename(file.filename)
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, filename)
            file.save(temp_path)

            logging.debug(f"File '{filename}' received and saved to a temporary location.")
            logging.debug(f"User email: {request.form.get('email')}, Timezone: {request.form.get('timezone')}")

            # Document AI setup (robust env var usage)
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
            processor_id = os.environ.get("DOCUMENT_AI_PROCESSOR_ID") or os.environ.get("PROCESSOR_ID")
            location = os.environ.get("DOCUMENT_AI_LOCATION") or "us"
            client = documentai.DocumentProcessorServiceClient()
            processor_path = client.processor_path(project_id, location, processor_id)

            with open(temp_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()

            raw_document = documentai.RawDocument(content=pdf_bytes, mime_type="application/pdf")
            request_ai = documentai.ProcessRequest(name=processor_path, raw_document=raw_document)
            result = client.process_document(request=request_ai)

            # Use Document.to_json for robust entity extraction
            from workschedule.services.ics_generator import extract_shifts_from_docai_entities, create_ics_from_entries
            import json
            document_json = documentai.Document.to_json(result.document)
            document_dict = json.loads(document_json)
            entities = document_dict.get('entities', [])
            logging.debug(f"Document AI entities: {json.dumps(entities, indent=2)}")

            schedule_entries = extract_shifts_from_docai_entities(entities)
            logging.debug(f"Parsed schedule entries: {json.dumps(schedule_entries, default=str, indent=2)}")

            ics_data = create_ics_from_entries(schedule_entries)
            global last_ics_data
            last_ics_data = ics_data

            os.remove(temp_path)
            return jsonify({
                'message': 'PDF processed successfully!',
                'document': document_dict.get('text', ''),
                'ics': ics_data,
                'schedule_entries': schedule_entries,
                'download_url': '/schedule/download_ics'
            }), 200
        except Exception as e:
            logging.error(f"Error processing upload: {e}")
            return jsonify({'error': 'An unexpected error occurred.'}), 500
    else:
        return jsonify({'error': 'Invalid file type. Please upload a PDF.'}), 400

# Route to download the latest ICS file
@schedule_bp.route('/download_ics', methods=['GET'])
@login_required
def download_ics():
    global last_ics_data
    if not last_ics_data:
        return jsonify({'error': 'No ICS file available. Please upload a schedule first.'}), 404
    return Response(
        last_ics_data,
        mimetype='text/calendar',
        headers={
            'Content-Disposition': 'attachment; filename="schedule.ics"'
        }
    )


