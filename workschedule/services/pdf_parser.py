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
{{
  "doc_type": "work_schedule | syllabus | project_plan | itinerary | meeting_schedule | other",
  "summary": "one sentence describing what the document is",
  "year": "4-digit year if determinable, else null",
  "subject": "employer/course/project name if present, else null",
  "location": "store number, campus, office, etc. if present, else null",
  "has_calendar_content": true or false
}}

Document text:
{text}"""


def _get_document_context(text: str) -> dict:
    """Pass 1: understand what the document is."""
    prompt = CONTEXT_PROMPT.format(text=text[:3000])
    try:
        response = _client().messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"[pdf_parser] Context pass failed: {e}")
        return {"has_calendar_content": True, "year": None, "location": "", "subject": ""}


# ---------------------------------------------------------------------------
# Pass 2 — Event extraction
# ---------------------------------------------------------------------------
EXTRACT_PROMPT = """You are a calendar assistant. Extract every shift/event from the schedule text below.

Context about this document:
- Type: {doc_type}
- Subject/Employer: {subject}
- Location/Store: {location}
- Year: {year}

Return ONLY a JSON array of objects with these exact keys (no extra keys, no markdown):
[
  {{
    "shift_date": "Mon, Sep 08",
    "shift_start": "11:30 AM",
    "shift_end": "8:00 PM",
    "department": "Plumbing & Bath Associate",
    "store_number": "0660"
  }}
]

Rules:
- shift_date format: abbreviated weekday, abbreviated month, zero-padded day (e.g. "Mon, Sep 08")
- shift_start / shift_end: 12-hour time with AM/PM (e.g. "11:30 AM", "8:00 PM")
- If no time (day off, holiday): use empty string "" for shift_start and shift_end
- department: role or department label; use empty string if not found
- store_number: store/location number; use empty string if not found
- Skip days off and non-work entries
- If the year is provided in context, use it to resolve any ambiguous dates

Schedule text:
{text}"""


def _extract_events(text: str, context: dict) -> list:
    """Pass 2: extract structured events from the document."""
    prompt = EXTRACT_PROMPT.format(
        doc_type=context.get("doc_type", "work_schedule"),
        subject=context.get("subject") or "",
        location=context.get("location") or "",
        year=context.get("year") or datetime.now().year,
        text=text[:6000]
    )
    try:
        response = _client().messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        logger.error(f"[pdf_parser] Extraction pass failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Validation helpers (exported so tests can import them directly)
# ---------------------------------------------------------------------------
REQUIRED_KEYS = {"shift_date", "shift_start", "shift_end", "department", "store_number"}

# Accepts "Mon, Sep 08" or "Sep 08" (weekday prefix optional)
DATE_RE = re.compile(r"^(?:[A-Z][a-z]{2}, )?[A-Z][a-z]{2} \d{2}$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2} [AP]M$")   # 12-hour only, e.g. "11:30 AM"


def _is_valid_date(value, year: str) -> bool:
    """Return True if value looks like a real calendar date string."""
    if not value or not isinstance(value, str):
        return False
    return bool(DATE_RE.match(value.strip()))


def _is_valid_time(value) -> bool:
    """Return True for a valid 12-hour time string OR empty string (all-day)."""
    if value is None:
        return False
    if value == "":
        return True   # empty = all-day event, valid
    return bool(TIME_RE.match(value.strip()))


def _is_meaningful_title(value) -> bool:
    """Return True if value is a non-trivial department/title string."""
    if not value or not isinstance(value, str):
        return False
    stripped = value.strip()
    if len(stripped) <= 1:
        return False
    if stripped.isdigit():
        return False
    return True


def _validate_events(events: list, context: dict) -> list:
    """Filter out malformed events and fill in missing store_number from context."""
    year = str(context.get("year") or datetime.now().year)
    default_store = context.get("location") or ""
    clean = []
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            logger.debug(f"[pdf_parser] Skipping non-dict event at index {i}")
            continue
        if not REQUIRED_KEYS.issubset(ev.keys()):
            logger.debug(f"[pdf_parser] Skipping event missing keys: {ev}")
            continue
        if not _is_valid_date(ev.get("shift_date"), year):
            logger.debug(f"[pdf_parser] Bad date: {ev.get('shift_date')}")
            continue
        start = ev.get("shift_start", "")
        end = ev.get("shift_end", "")
        if not _is_valid_time(start):
            logger.debug(f"[pdf_parser] Bad start time: {start}")
            continue
        if not _is_valid_time(end):
            logger.debug(f"[pdf_parser] Bad end time: {end}")
            continue
        # Reject mismatched times: one set, the other empty
        if bool(start) != bool(end):
            logger.debug(f"[pdf_parser] Mismatched times start={start!r} end={end!r}")
            continue
        # Require a meaningful department/title
        if not _is_meaningful_title(ev.get("department")):
            logger.debug(f"[pdf_parser] No meaningful title: {ev.get('department')!r}")
            continue
        # Fill in store number from context if blank
        if not ev.get("store_number") and default_store:
            ev["store_number"] = default_store
        clean.append(ev)
    return clean


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse_document(text: str) -> list:
    """
    Takes raw text extracted from a PDF and returns
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

    logger.info(f"[pdf_parser] Parsed {len(validated)} events from document")
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
