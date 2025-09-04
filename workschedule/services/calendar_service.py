import uuid
from datetime import datetime
from icalendar import Calendar, Event, vCalAddress, vText

def generate_ics_file(work_schedule, timezone_str):
    """
    Generates an .ics file (iCalendar format) from a work schedule.

    Args:
        work_schedule (dict): A dictionary representing the work schedule.
                              Expected format:
                              {
                                'events': [
                                    {'start_time': datetime object, 'end_time': datetime object, 'summary': 'Event Title'},
                                    ...
                                ]
                              }
        timezone_str (str): The timezone for the events (e.g., 'America/Los_Angeles').

    Returns:
        str: A string containing the iCalendar data.
    """
    try:
        cal = Calendar()
        cal.add('prodid', '-//WorkSchedule.cloud//EN')
        cal.add('version', '2.0')

        # Set the timezone for the calendar
        cal.add('X-WR-TIMEZONE', vText(timezone_str))

        for event_data in work_schedule.get('events', []):
            event = Event()
            event.add('summary', event_data['summary'])
            event.add('dtstart', event_data['start_time'])
            event.add('dtend', event_data['end_time'])
            event.add('dtstamp', datetime.now())
            event['uid'] = str(uuid.uuid4()) + '@workschedule.cloud'
            cal.add_component(event)

        return cal.to_ical().decode('utf-8')
    except Exception as e:
        # Log the error for debugging purposes
        print(f"Error generating .ics file: {e}")
        return ""

# Example usage (for local testing)
if __name__ == '__main__':
    # Sample work schedule data
    sample_schedule = {
        'events': [
            {
                'start_time': datetime(2025, 9, 4, 9, 0, 0),
                'end_time': datetime(2025, 9, 4, 17, 0, 0),
                'summary': 'Morning Shift'
            },
            {
                'start_time': datetime(2025, 9, 5, 13, 0, 0),
                'end_time': datetime(2025, 9, 5, 21, 0, 0),
                'summary': 'Evening Shift'
            }
        ]
    }
    
    # Generate and print the .ics content
    ics_output = generate_ics_file(sample_schedule, 'America/New_York')
    print(ics_output)

