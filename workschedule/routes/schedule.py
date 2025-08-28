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

            # Document AI setup
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = "us"  # or your processor's location
            processor_id = os.environ.get("DOCUMENT_AI_PROCESSOR_ID")
            client = documentai.DocumentProcessorServiceClient()
            processor_path = client.processor_path(project_id, location, processor_id)

            with open(temp_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()

            raw_document = documentai.RawDocument(content=pdf_bytes, mime_type="application/pdf")
            request_ai = documentai.ProcessRequest(name=processor_path, raw_document=raw_document)
            result = client.process_document(request=request_ai)

            # Log only the entities for debugging
            try:
                entities_list = getattr(result.document, 'entities', [])
                entities_json = [
                    {
                        "type_": getattr(e, "type_", None),
                        "mention_text": getattr(e, "mention_text", None),
                        "confidence": getattr(e, "confidence", None)
                        # Add other fields as needed
                    }
                    for e in entities_list
                ]
                logging.debug(f"Document AI entities: {json.dumps(entities_json, indent=2)}")
            except Exception as log_exc:
                logging.error(f"Error logging Document AI entities: {log_exc}")

            # Use Document AI labeled entities for ICS generation
            from workschedule.services.ics_generator import extract_shifts_from_docai_entities, create_ics_from_entries

            # Robustly extract entities as a list
            raw_entities = getattr(result.document, 'entities', None)
            if raw_entities is None:
                entities = []
            elif isinstance(raw_entities, list):
                entities = [e.to_dict() if hasattr(e, 'to_dict') else dict(e) for e in raw_entities]
            else:
                # If it's a single entity, wrap in a list
                try:
                    entities = [raw_entities.to_dict() if hasattr(raw_entities, 'to_dict') else dict(raw_entities)]
                except Exception:
                    entities = []

            schedule_entries = extract_shifts_from_docai_entities(entities)

            ics_data = create_ics_from_entries(schedule_entries)
            global last_ics_data
            last_ics_data = ics_data

            os.remove(temp_path)
            return jsonify({
                'message': 'PDF processed successfully!',
                'document': result.document.text,
                'ics': ics_data,
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


