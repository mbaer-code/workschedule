# src/routes/schedule.py
# This file defines the blueprint for schedule-related routes.

import os
from flask import Blueprint, render_template, request, jsonify
from werkzeug.utils import secure_filename

# Create a Blueprint instance
schedule_bp = Blueprint('schedule_bp', __name__, url_prefix='/schedule')

@schedule_bp.route('/upload', methods=['GET'])
def upload_form():
    """
    Renders the PDF upload form.
    """
    return render_template('upload.html')

@schedule_bp.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    """
    Handles the POST request for a PDF file upload.
    This is the backend logic for Session 5.
    
    It performs initial validation and a placeholder action.
    The actual Document AI processing will be implemented in a later session.
    """
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['pdf_file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and file.filename.endswith('.pdf'):
        try:
            # Placeholder: In the next step, this is where you'll
            # integrate the Document AI client.
            filename = secure_filename(file.filename)
            temp_path = os.path.join('/tmp', filename)
            file.save(temp_path)
            
            print(f"File '{filename}' received and saved to a temporary location.")
            print(f"User email: {request.form.get('email')}, Timezone: {request.form.get('timezone')}")
            
            # This is the line you'll replace in S6 to process the PDF
            print("Placeholder: Document AI processing logic will go here.")

            os.remove(temp_path)

            return jsonify({'message': 'PDF uploaded successfully! Processing your schedule now.'}), 200

        except Exception as e:
            # Log the error to Cloud Logging
            print(f"Error processing upload: {e}")
            return jsonify({'error': 'An unexpected error occurred.'}), 500
    else:
        return jsonify({'error': 'Invalid file type. Please upload a PDF.'}), 400


