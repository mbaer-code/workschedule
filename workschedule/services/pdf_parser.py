"""
pdf_parser.py
-------------
AI-powered document parser that replaces the regex-based parse_schedule_text().

Two-pass approach:
  Pass 1 - Understand the document: what kind is it, what year/context applies
  Pass 2 - Extract calendar-worthy events given that context

Output format matches what the rest of the pipeline (ics_generator.py) expects:
  {
      'shift_date':   'Mon, Sep 08',   # strftime('%a, %b %d')
      'shift_start':  '11:30 AM',      # or '' if all-day
      'shift_end':    '8:00 PM',       # or '' if all-day
      'department':   'Plumbing',      # role/subject/context label
      'store_number': '0660'           # location/section/code or ''
  }

Drop-in replacement: just swap parse_schedule_text(text) for parse_document(text).
"""

import json
import logging
import os
import re
from datetime import datetime

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Anthropic client (API key from environment)
# ---------------------------------------------------------------------------
def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")
    return anthropic.Anthropic(api_key=api_key)


MODEL = "claude-haiku-4-5-20251001"   # cheap, fast, accurate enough


# ---------------------------------------------------------------------------
# Pass 1 — Document context
# ---------------------------------------------------------------------------
CONTEXT_PROMPT = """You are a document analyst. Read the text below and return ONLY a JSON object — no explanation, no markdown.

Return this exact structure:
{
  "doc_type": "work_schedule | syllabus | project_plan | itinerary | meeting_schedule | other",
  "summary": "one sentence describing what the document is",
  "year": "4-digit year if determinable, else null",
  "subject": "employer/course/project name if present, else null",
  "location": "store number, campus, office, etc. if present, else null",
  "has_calendar_content": true or false
}

Document text:
{text}"""


def _get_document_context(text: str) -> dict:
    """Pass 1: understand what the document is."""
    prompt = CONTEXT_PROMPT.format(text=text[:3000])  # first 3000 chars is enough
    try:
        response = _client().messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if model adds them
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        ctx = json.loads(raw)
        logger.info(f"[pdf_parser] Document context: {ctx}")
        return ctx
    except Exception as e:
        logger.warning(f"[pdf_parser] Context pass failed: {e}")
        return {
            "doc_type": "other",
            "summary": "Unknown document",
            "year": None,
            "subject": None,
            "location": None,
            "has_calendar_content": True   # try anyway
        }


# ---------------------------------------------------------------------------
# Pass 2 — Event extraction
# ---------------------------------------------------------------------------
EXTRACT_PROMPT = """You are a calendar assistant. Extract every calendar-worthy event from the document below.

Document context: {summary}
Document type: {doc_type}
Year (use this if dates lack a year): {year}
Subject/Employer/Course: {subject}
Location/Store/Campus: {location}

Rules:
- Only extract events a person would actually put in a calendar.
- A date is only calendar-worthy if it has a meaningful associated event or action.
- Ignore: version numbers, figure references, page numbers, copyright years, document metadata.
- If an event has a specific time range, include start and end times.
- If an event is all-day (deadline, due date, exam day), leave start_time and end_time as empty strings.
- For work shifts: title should be the employer name or department.
- For syllabus: title should be the assignment or exam name.
- For project docs: title should be the milestone or deliverable name.
- Use the provided year if dates in the document don't include one.
- If the document spans multiple years, infer the correct year from context.
- Format dates as "Mon, Sep 08" (strftime %a, %b %d). Use 2-digit day.
- Format times as "11:30 AM" or "8:00 PM" (12-hour with space before AM/PM).

Return ONLY a JSON array, no explanation, no markdown:
[
  {{
    "shift_date":   "Mon, Sep 08",
    "shift_start":  "11:30 AM",
    "shift_end":    "8:00 PM",
    "department":   "descriptive label (role, subject, milestone, etc.)",
    "store_number": "location/store/section code or empty string"
  }},
  ...
]

If no calendar-worthy events are found, return an empty array: []

Document text:
{text}"""


def _extract_events(text: str, context: dict) -> list:
    """Pass 2: extract calendar events given document context."""
    year = context.get("year") or str(datetime.now().year)
    prompt = EXTRACT_PROMPT.format(
        summary=context.get("summary", "Unknown document"),
        doc_type=context.get("doc_type", "other"),
        year=year,
        subject=context.get("subject") or "not specified",
        location=context.get("location") or "not specified",
        text=text[:6000]   # Haiku context is generous; 6k chars covers most PDFs
    )
    try:
        response = _client().messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        events = json.loads(raw)
        if not isinstance(events, list):
            logger.warning("[pdf_parser] Extraction returned non-list, defaulting to []")
            return []
        logger.info(f"[pdf_parser] Extracted {len(events)} raw events")
        return events
    except Exception as e:
        logger.error(f"[pdf_parser] Extraction pass failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _is_valid_date(date_str: str, year: str) -> bool:
    """Check the date string is a real calendar date."""
    if not date_str:
        return False
    # Try parsing — accepts "Mon, Sep 08" format
    for fmt in ("%a, %b %d", "%b %d", "%B %d"):
        try:
            datetime.strptime(date_str.strip(), fmt)
            return True
        except ValueError:
            continue
    return False


def _is_valid_time(time_str: str) -> bool:
    """Check time string is parseable or empty (all-day events allowed)."""
    if not time_str:
        return True   # all-day is valid
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            datetime.strptime(time_str.strip(), fmt)
            return True
        except ValueError:
            continue
    return False


def _is_meaningful_title(department: str) -> bool:
    """Reject entries with no useful label."""
    if not department or not department.strip():
        return False
    # Reject if it looks like a number-only label
    if re.match(r'^\d+$', department.strip()):
        return False
    if len(department.strip()) < 2:
        return False
    return True


def _validate_events(events: list, context: dict) -> list:
    """Filter out entries that wouldn't make sense as calendar events."""
    year = context.get("year") or str(datetime.now().year)
    valid = []
    for entry in events:
        date_str = entry.get("shift_date", "")
        start = entry.get("shift_start", "")
        end = entry.get("shift_end", "")
        dept = entry.get("department", "")

        if not _is_valid_date(date_str, year):
            logger.info(f"[pdf_parser] SKIP invalid date: {entry}")
            continue
        if not _is_valid_time(start):
            logger.info(f"[pdf_parser] SKIP invalid start time: {entry}")
            continue
        if not _is_valid_time(end):
            logger.info(f"[pdf_parser] SKIP invalid end time: {entry}")
            continue
        if not _is_meaningful_title(dept):
            logger.info(f"[pdf_parser] SKIP no meaningful title: {entry}")
            continue
        # If there's a start time there must be an end time and vice versa
        if bool(start) != bool(end):
            logger.info(f"[pdf_parser] SKIP mismatched start/end: {entry}")
            continue

        valid.append({
            "shift_date":   date_str.strip(),
            "shift_start":  start.strip(),
            "shift_end":    end.strip(),
            "department":   dept.strip(),
            "store_number": str(entry.get("store_number", "")).strip()
        })

    logger.info(f"[pdf_parser] {len(valid)} valid events after validation")
    return valid


# ---------------------------------------------------------------------------
# Public API — drop-in replacement for parse_schedule_text()
# ---------------------------------------------------------------------------
def parse_document(text: str) -> list:
    """
    Main entry point. Takes raw text extracted from a PDF and returns
    a list of calendar-ready event dicts.

    Drop-in replacement for parse_schedule_text() in the routes file.
    """
    if not text or len(text.strip()) < 20:
        logger.warning("[pdf_parser] Text too short to parse")
        return []

    # Pass 1: understand the document
    context = _get_document_context(text)

    if not context.get("has_calendar_content", True):
        logger.info("[pdf_parser] Document has no calendar content per context pass")
        return []

    # Pass 2: extract events
    events = _extract_events(text, context)

    # Validate
    validated = _validate_events(events, context)

    return validated


# ---------------------------------------------------------------------------
# Convenience: get document summary for UI display
# ---------------------------------------------------------------------------
def get_document_summary(text: str) -> str:
    """
    Returns a one-sentence human-readable summary of the document.
    Useful for showing the user "We detected a work schedule for Home Depot, Store 0660"
    before they confirm the calendar entries.
    """
    context = _get_document_context(text)
    summary = context.get("summary", "")
    subject = context.get("subject")
    location = context.get("location")
    extras = ", ".join(filter(None, [subject, location]))
    if extras:
        return f"{summary} ({extras})"
    return summary
