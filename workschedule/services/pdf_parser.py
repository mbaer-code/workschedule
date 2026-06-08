import os
import datetime
import json
import logging

import fitz  # PyMuPDF
import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a calendar event extractor. Your job is to read any document \
and extract all dates and events into structured calendar data.

Classify the document and extract events appropriate to its type:
- work_schedule: shifts with start/end times
- syllabus: assignments, exams, class sessions, deadlines
- legal: deadlines, hearings, response dates
- project: milestones, deliverables, meetings
- general: any date-referenced event or deadline

Rules:
- title: short, max 30 characters, what the event IS
- context: the source document name or organization, used in description
- For recurring events (e.g. "class meets MWF"), expand into individual events
- For all-day events with no time, set all_day true and omit times
- Include person's name in title if multiple people's schedules are present
- Year ambiguity: assume nearest future occurrence relative to today's date
- If the document appears to be a scanned image with no extractable text, \
return an empty events array and set confidence to "low"
- Deduplicate: if the same date and event appears more than once, include it only once
- For academic calendars with "Key Dates" and per-session breakdown sections, extract only from the "Key Dates" sections — skip the redundant per-session deadline breakdowns
- Cap output at 60 events maximum; if more exist, keep the most student-relevant ones
- Return ONLY valid JSON, no preamble, no markdown fences

Return this exact structure:
{
  "document_type": "work_schedule|syllabus|legal|project|general",
  "document_title": "brief descriptive title of the source document",
  "confidence": "high|medium|low",
  "events": [
    {
      "title": "short event title, 30 chars max",
      "context": "source document or organization name",
      "date": "YYYY-MM-DD",
      "start_time": "HH:MM" or null,
      "end_time": "HH:MM" or null,
      "all_day": true or false,
      "notes": "any useful context" or null
    }
  ]
}"""

USER_PROMPT_TEMPLATE = """Today's date is {today}.
Use this to resolve relative dates and year ambiguity — \
assume the nearest future occurrence of any undated event.

Extract all calendar events from this document:

{extracted_text}"""


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return ""


def _fmt_time(t: str) -> str:
    """Convert 24h 'HH:MM' to 12h 'H:MM AM/PM' as expected by ics_generator."""
    dt = datetime.datetime.strptime(t, "%H:%M")
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.strftime('%M')} {ampm}"


def parse_pdf_with_claude(pdf_bytes: bytes) -> list:
    """
    Extract calendar events from a PDF using Claude Haiku.
    Returns a list of dicts compatible with create_ics_from_entries.
    """
    MAX_INPUT_CHARS = 24_000

    text = extract_text_from_pdf(pdf_bytes)
    if not text or len(text.strip()) < 20:
        logger.warning("No extractable text in PDF")
        return []

    if len(text) > MAX_INPUT_CHARS:
        logger.warning(f"Document too long ({len(text)} chars), exceeds {MAX_INPUT_CHARS} limit")
        raise ValueError(
            "This document is too long to process. Please upload a shorter document."
        )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    today = datetime.date.today().isoformat()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_PROMPT_TEMPLATE.format(
            today=today,
            extracted_text=text
        )}]
    )

    usage = response.usage
    logger.info(f"Haiku usage: input={usage.input_tokens} output={usage.output_tokens}")

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Haiku returned invalid JSON: {e}\nRaw: {raw[:500]}")
        raise ValueError("AI parser returned an unreadable response. Please try again.")

    doc_type = result.get("document_type", "unknown")
    doc_title = result.get("document_title", "")
    confidence = result.get("confidence", "unknown")
    events = result.get("events", [])

    logger.info(f"Document: type={doc_type!r} title={doc_title!r} confidence={confidence} events={len(events)}")

    entries = []
    for ev in events:
        try:
            date_str = ev.get("date")
            if not date_str:
                continue
            date_obj = datetime.date.fromisoformat(date_str)
            shift_date = date_obj.strftime("%a, %b %d")

            all_day = ev.get("all_day", False)
            start_raw = ev.get("start_time")
            end_raw = ev.get("end_time")

            if all_day or not start_raw:
                shift_start = ""
                shift_end = ""
            else:
                shift_start = _fmt_time(start_raw)
                shift_end = _fmt_time(end_raw) if end_raw else shift_start

            # For work schedules use a neutral title; other types keep Haiku's title
            if doc_type == "work_schedule":
                event_title = "Work Shift"
            else:
                event_title = ev.get("title", "Event")

            # Trim context to the first segment before " - " to avoid verbose suffixes
            context = ev.get("context", "")
            if " - " in context:
                context = context.split(" - ")[0].strip()
            # Cap at 40 chars for display
            if len(context) > 40:
                context = context[:38].rstrip() + "…"

            entries.append({
                "shift_date": shift_date,
                "shift_start": shift_start,
                "shift_end": shift_end,
                "department": context,
                "store_number": "",
                "event_title": event_title,
                "all_day": all_day,
            })
        except Exception as e:
            logger.warning(f"Skipping malformed event {ev}: {e}")
            continue

    return entries, doc_title
