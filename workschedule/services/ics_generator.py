import json
import re
from datetime import datetime, timedelta, time, timezone
import uuid
import logging
from icalendar import Calendar, Event
import hashlib

# Set up basic logging for internal messages and debugging.
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# The JSON data from your Document AI output.
# In a real-world scenario, you would replace this with the actual
# JSON output from your Document AI processing.
document_ai_json_data = [
    {
        "type": "Work-shift",
        "confidence": 1.0,
        "id": "69",
        "properties": [
            {
                "type": "Shift-date",
                "mentionText": "Sep\n9",
                "confidence": 0.97296906,
                "id": "70"
            }
        ]
    },
    {
        "type": "Work-shift",
        "confidence": 1.0,
        "id": "71",
        "properties": [
            {
                "type": "Shift-date",
                "mentionText": "Sep\n10",
                "confidence": 0.999549,
                "id": "72"
            }
        ]
    },
    {
        "type": "Work-shift",
        "confidence": 1.0,
        "id": "73",
        "properties": [
            {
                "type": "Department",
                "mentionText": "Plumbing & Bath Associate",
                "confidence": 0.9994467,
                "id": "74"
            },
            {
                "type": "Shift-date",
                "mentionText": "Sep 11",
                "confidence": 0.9883951,
                "id": "75"
            },
            {
                "type": "Shift-end",
                "mentionText": "8:00 PM",
                "confidence": 0.9999491,
                "id": "76"
            },
            {
                "type": "Start-start",
                "mentionText": "11:30 AM",
                "confidence": 0.9999976,
                "id": "77"
            },
            {
                "type": "Store-number",
                "mentionText": "0660",
                "confidence": 0.9999994,
                "id": "78"
            }
        ]
    },
    {
        "type": "Work-shift",
        "confidence": 1.0,
        "id": "79",
        "properties": [
            {
                "type": "Shift-date",
                "mentionText": "Sep\n12",
                "confidence": 0.99987066,
                "id": "80"
            }
        ]
    },
    {
        "type": "Work-shift",
        "confidence": 1.0,
        "id": "81",
        "properties": [
            {
                "type": "Shift-date",
                "mentionText": "Sep\n13",
                "confidence": 0.9999411,
                "id": "82"
            }
        ]
    }
]

def extract_shifts_from_docai_entities(entities):
    """
    Parses Document AI entities to find and extract work shift information.
    It handles finding the year from other entities and combines
    relevant properties into a single shift entry.
    
    Args:
        entities (list): A list of dictionaries representing Document AI entities.

    Returns:
        list: A list of dictionaries, where each dictionary represents a
              parsed work shift with keys like 'date', 'start_time', etc.
    """
    shifts = []
    # Try to get year from date range entity, which is a great improvement.
    year = None
    for entity in entities:
        if entity.get('type_') in ['PageDateRange', 'DocumentTitle']:
            text = entity.get('mention_text', '')
            year_match = re.search(r'(\d{4})', text)
            if year_match:
                year = year_match.group(1)
                break
    
    # If no year is found, default to the current year.
    if not year:
        year = str(datetime.now().year)
    
    seen = set()
    
    # Iterate through the top-level entities to find work shifts.
    for entity in entities:
        entity_type = entity.get('type') or entity.get('type_')
        
        # Check if the entity is a work shift.
        if entity_type == 'Work-shift':
            properties = entity.get('properties', [])
            
            # Log the processing of each work-shift entity for debugging.
            page_num = None
            if 'pageAnchor' in entity:
                page_refs = entity['pageAnchor'].get('pageRefs', [])
                if page_refs and 'page' in page_refs[0]:
                    page_num = page_refs[0]['page']
            logging.info(f"Processing Work-shift entity on page: {page_num}, id: {entity.get('id')}")

            if not properties:
                continue

            shift_data = {}
            # Extract key properties from the current work shift entity.
            for prop in properties:
                prop_type = (prop.get('type') or prop.get('type_') or '').lower()
                mention = prop.get('mentionText') or prop.get('mention_text', '')

                if prop_type in ['shift-date', 'date']:
                    shift_data['date_str'] = mention.replace('\n', ' ').strip()
                elif prop_type in ['start-shift', 'start-start']:
                    shift_data['start_time'] = mention.strip()
                elif prop_type == 'shift-end':
                    shift_data['end_time'] = mention.strip()
                elif prop_type == 'store-number':
                    shift_data['role'] = mention.strip()
                elif prop_type == 'department':
                    shift_data['department'] = mention.strip()
                elif prop_type == 'shift-total':
                    shift_data['shift_total'] = mention.strip()

            try:
                date_obj = None
                if 'date_str' in shift_data:
                    date_str = shift_data['date_str']
                    date_obj = datetime.strptime(f"{date_str} {year}", "%b %d %Y")
                
                # We need a date, start time, and end time to create a full event.
                if not date_obj:
                    logging.info(f"SKIP: No valid date for shift entity: {shift_data}")
                    continue
                if not shift_data.get('start_time') or not shift_data.get('end_time'):
                    logging.info(f"SKIP: Missing start or end time for shift entity: {shift_data}")
                    continue

            except Exception as e:
                logging.info(f"SKIP: Date parsing failed for shift entity: {shift_data}, error: {e}")
                continue

            # Deduplication key to prevent duplicate calendar entries.
            dedup_key = f"{date_obj.date()}_{shift_data.get('start_time','').strip()}"
            if dedup_key in seen:
                logging.info(f"SKIP: Duplicate shift for key {dedup_key}: {shift_data}")
                continue
            seen.add(dedup_key)

            # Create a structured entry for the valid shift.
            shift_entry = {
                'date': date_obj,
                'start_time': shift_data.get('start_time',''),
                'end_time': shift_data.get('end_time',''),
                'role': shift_data.get('role',''),
                'department': shift_data.get('department',''),
                'shift_total': shift_data.get('shift_total','')
            }
            logging.info(f"INCLUDE: Extracted shift entry: {shift_entry}")
            shifts.append(shift_entry)

    return shifts

def create_ics_from_entries(entries, calendar_name="work-schedule", timezone_str=None):
    """
    Given a list of shift entries, generate an ICS calendar file as a string.
    This function uses the iCalendar library for robust file creation.

    Args:
        entries (list): A list of dictionaries, each representing a work shift.
        calendar_name (str): The name to display for the calendar.

    Returns:
        str: The content of the iCalendar file.
    """
    print(f"[DEBUG] create_ics_from_entries: received entries={entries}")
    print(f"[DEBUG] create_ics_from_entries: entries count={len(entries)}")
    cal = Calendar()
    cal.add('prodid', '-//Workforce Schedule//mxm.dk//')
    cal.add('version', '2.0')
    cal.add('method', 'PUBLISH')
    cal.add('X-WR-CALNAME', calendar_name)

    import pytz
    tzinfo = None
    if timezone_str:
        try:
            tzinfo = pytz.timezone(timezone_str)
        except Exception:
            tzinfo = None

    for entry in entries:
        # Parse date from 'shift_date' (e.g., 'Mon, Sep 08') and add current year
        try:
            date_str = entry.get('shift_date', '')
            date_obj = datetime.strptime(f"{date_str} {datetime.now().year}", "%a, %b %d %Y")
        except Exception as e:
            print(f"[DEBUG] Failed to parse shift_date '{entry.get('shift_date')}' with error: {e}")
            continue
        start_time = entry.get('shift_start', '')
        end_time = entry.get('shift_end', '')
        if not start_time or not end_time:
            print(f"[DEBUG] Missing start or end time for entry: {entry}")
            continue
        start_dt = combine_date_time(date_obj, start_time)
        end_dt = combine_date_time(date_obj, end_time)
        if tzinfo:
            start_dt = tzinfo.localize(start_dt)
            end_dt = tzinfo.localize(end_dt)
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        event = Event()
        event.add('summary', entry.get('department', 'Work Shift'))
        event.add('dtstart', start_dt)
        event.add('dtend', end_dt)
        now_utc = datetime.now(timezone.utc)
        event.add('dtstamp', now_utc)
        event.add('last-modified', now_utc)
        description_parts = [f"{start_time} - {end_time}", date_obj.strftime('%A, %b %d, %Y')]
        if entry.get('department'):
            description_parts.append(entry['department'])
        if entry.get('store_number'):
            description_parts.append(f"Store: {entry['store_number']}")
        event.add('description', '\n'.join(description_parts))
        uid_source = f"{date_obj.isoformat()}-{start_time}-{end_time}-{entry.get('department')}-{entry.get('store_number')}"
        uid_hash = hashlib.sha1(uid_source.encode('utf-8')).hexdigest()
        event.add('uid', uid_hash)
        cal.add_component(event)

    return cal.to_ical().decode('utf-8')

def combine_date_time(date_obj, time_str):
    """
    Combines a date object and a time string (e.g., '12:30 PM') into a datetime object.
    
    Args:
        date_obj (datetime.datetime): A date object.
        time_str (str): A time string in the format '%I:%M %p' or '%I %p'.

    Returns:
        datetime.datetime: The combined datetime object.
    """
    try:
        time_obj = datetime.strptime(time_str, '%I:%M %p').time()
    except ValueError:
        try:
            time_obj = datetime.strptime(time_str, '%I %p').time()
        except ValueError:
            logging.error(f"Failed to parse time string: {time_str}")
            time_obj = time(0, 0)  # Default to midnight if parsing fails.
    return datetime.combine(date_obj.date(), time_obj)

if __name__ == "__main__":
    # --- Main Execution Flow ---
    
    # 1. Extract shift data from the raw Document AI entities.
    logging.info("Starting extraction of shifts from Document AI entities...")
    extracted_shifts = extract_shifts_from_docai_entities(document_ai_json_data)
    logging.info(f"Successfully extracted {len(extracted_shifts)} complete shifts.")
    
    # 2. Convert the extracted shift data into a complete ICS file string.
    logging.info("Generating ICS file content...")
    ics_file_content = create_ics_from_entries(extracted_shifts)
    
    # 3. Print the final ICS file content.
    if ics_file_content:
        print("\n" + "="*50)
        print("Generated ICS File Content")
        print("="*50)
        print(ics_file_content)
        print("="*50)
        
        # Optional: Save the content to a file.
        # with open("shifts.ics", "w") as f:
        #     f.write(ics_file_content)
        # print("File saved as 'shifts.ics'")
    else:
        print("No complete shifts were found to generate an ICS file.")

