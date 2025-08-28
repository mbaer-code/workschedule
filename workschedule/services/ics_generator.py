import os
import re
import hashlib
from datetime import datetime, timedelta
from icalendar import Calendar, Event
from flask import Flask, request, Response
from google.cloud import documentai_v1 as documentai

# --- Document AI and Data Extraction Logic ---

def extract_shifts_from_docai_entities(entities):
    """
    Extracts shift information from Document AI entities, leveraging nested
    properties and normalized values.
    """
    shifts = []
    # Try to get the year from a top-level entity like PageDateRange
    year = None
    for entity in entities:
        if entity.get('type_') in ['PageDateRange', 'DocumentTitle']:
            text = entity.get('mention_text', '')
            year_match = re.search(r'(\d{4})', text)
            if year_match:
                year = year_match.group(1)
                break
    # Default to current year if not found
    if not year:
        year = str(datetime.now().year)
    
    # Iterate through entities to find the main shift entries
    for entity in entities:
        if entity.get('type_') == 'ShiftEntry':
            shift_data = {
                'date': None,
                'start_time': None,
                'end_time': None,
                'role': None,
                'department': None,
                'shift_total': None,
            }
            
            # Since your model extracts a single 'ShiftEntry' entity with a lot of text,
            # it's likely your model is extracting all sub-fields as properties.
            # We'll need to check the 'properties' of the 'ShiftEntry' entity.
            properties = entity.get('properties', [])
            
            # Extract date, start, and end.
            for prop in properties:
                prop_type = prop.get('type_')
                
                if prop_type == 'day':
                    day_mention_text = prop.get('mention_text')
                    month_mention_text = ''
                    for month_prop in properties:
                        if month_prop.get('type_') == 'month':
                            month_mention_text = month_prop.get('mention_text')
                            break

                    if month_mention_text and day_mention_text:
                        try:
                            # Combine to create a date object
                            date_str = f"{month_mention_text} {day_mention_text} {year}"
                            shift_data['date'] = datetime.strptime(date_str, "%b %d %Y")
                        except ValueError:
                            # Skip if date is invalid
                            continue
                
                elif prop_type == 'ShiftStart':
                    shift_data['start_time'] = prop.get('mention_text')
                
                elif prop_type == 'ShiftEnd':
                    shift_data['end_time'] = prop.get('mention_text')
                
                elif prop_type == 'StoreNumber':
                    shift_data['role'] = prop.get('mention_text')
                
                elif prop_type == 'Department':
                    shift_data['department'] = prop.get('mention_text')
                
                elif prop_type == 'ShiftTotal':
                    shift_data['shift_total'] = prop.get('mention_text')
                    
            # Only add to the list if essential data is found
            if shift_data['date'] and shift_data['start_time'] and shift_data['end_time']:
                shifts.append(shift_data)

    return shifts

# --- ICS Generation Utility (Your existing code) ---

def combine_date_time(date_obj, time_str):
    """
    Combines a date object and a time string like '12:30 PM' into a datetime object.
    """
    try:
        time_obj = datetime.strptime(time_str, '%I:%M %p').time()
    except Exception:
        try:
            time_obj = datetime.strptime(time_str, '%I %p').time()
        except Exception:
            time_obj = datetime.min.time()
    return datetime.combine(date_obj.date(), time_obj)

def create_ics_from_entries(entries, calendar_name="work-schedule-cloud"):
    """
    Given a list of entries, generate an ICS calendar file as a string.
    """
    cal = Calendar()
    cal.add('prodid', '-//Workforce Schedule//mxm.dk//')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', calendar_name)
    
    unique_by_date = {}
    for entry in entries:
        date_key = entry['date'].date() if isinstance(entry['date'], datetime) else entry['date']
        if date_key not in unique_by_date:
            unique_by_date[date_key] = entry
            
    for entry in unique_by_date.values():
        event = Event()
        start_dt = combine_date_time(entry['date'], entry['start_time'])
        end_dt = combine_date_time(entry['date'], entry['end_time'])
        
        summary_parts = ['THD']
        if entry.get('role'):
            summary_parts.append(entry['role'])
        if entry.get('department') and entry['department'] != entry.get('role'):
            summary_parts.append(entry['department'])
        event.add('summary', ' | '.join(summary_parts))
        
        event.add('dtstart', start_dt)
        event.add('dtend', end_dt)
        
        description_parts = []
        if entry.get('shift_total'):
            description_parts.append(f"Shift Total: {entry['shift_total']}")
        if entry.get('meal_start') and entry.get('meal_end'):
            description_parts.append(f"Meal: {entry['meal_start']} - {entry['meal_end']}")
        event.add('description', ' | '.join(description_parts))
        
        uid_fields = [
            'THD',
            entry.get('role', ''),
            entry.get('department', ''),
            start_dt.isoformat(),
            end_dt.isoformat(),
            calendar_name,
            entry.get('shift_total', ''),
        ]
        uid_source = '-'.join(str(f) for f in uid_fields)
        uid_hash = hashlib.sha1(uid_source.encode('utf-8')).hexdigest()
        event.add('uid', uid_hash)
        
        cal.add_component(event)
        
    return cal.to_ical().decode('utf-8')

# --- Cloud Run Flask Application ---

app = Flask(__name__)

# Replace with your actual project ID, location, and processor ID
PROJECT_ID=os.environ.get('GOOGLE_CLOUD_PROJECT')
LOCATION=os.environ.get('DOCUMENT_AI_LOCATION')
PROCESSOR_ID = os.environ.get('DOCUMENT_AI_PROCESSOR_ID')

def process_document_ai(file_path):
    """Processes a document using the Document AI API."""
    client_options = {"api_endpoint": f"{LOCATION}-documentai.googleapis.com"}
    docai_client = documentai.DocumentProcessorServiceClient(client_options=client_options)
    resource_name = docai_client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)
    
    with open(file_path, "rb") as image_file:
        image_content = image_file.read()
    
    raw_document = documentai.RawDocument(
        content=image_content, mime_type="application/pdf"
    )
    request = documentai.ProcessRequest(name=resource_name, raw_document=raw_document)
    result = docai_client.process_document(request=request)
    
    return result.document.entities

@app.route('/upload-and-convert', methods=['POST'])
def upload_and_convert():
    """
    Accepts a PDF file upload, processes it with Document AI, and returns an ICS file.
    """
    if 'file' not in request.files:
        return 'No file part in the request', 400
        
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
        
    # Securely save the file to a temporary location
    file_path = os.path.join('/tmp', file.filename)
    file.save(file_path)
    
    try:
        # Step 1: Process the document with your trained AI
        doc_ai_entities = process_document_ai(file_path)
        
        # Step 2: Extract the shift data from the Document AI entities
        extracted_shifts = extract_shifts_from_docai_entities(doc_ai_entities)
        
        if not extracted_shifts:
            return "No shift information could be extracted from the document.", 404
        
        # Step 3: Create the ICS file content
        ics_content = create_ics_from_entries(extracted_shifts)
        
        # Return the ICS file with the correct MIME type
        response = Response(
            ics_content,
            mimetype='text/calendar',
            headers={'Content-Disposition': 'attachment; filename=schedule.ics'}
        )
        return response

    except Exception as e:
        return {'error': str(e)}, 500
    finally:
        # Clean up the temporary file
        os.remove(file_path)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

