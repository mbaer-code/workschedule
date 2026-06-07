import os
import datetime
import json
import logging
import fitz
import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a calendar event extractor. Your job is to read any document and extract every date-based event, shift, deadline, or occurrence into a structured JSON format.

First, classify the document. Then extract all events.

Return a single JSON object with this exact structure:
{
  "document_type": "work_schedule | academic_calendar | legal_notice | itinerary | project_plan | meeting_schedule | other",
  "document_title": "concise title for the document, e.g. 'Home Depot Schedule Sep 8-14' or 'Fall 2024 Syllabus'",
  "confidence": "high | medium | low",
  "events": [
    {
      "date": "YYYY-MM-DD",
      "title": "short event name (5 words max)",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "all_day": false,
      "context": "dept, location, or other brief label"
    }
  ]
}

Rules:
- date: always ISO 8601 format YYYY-MM-DD
- title: short and specific — e.g. "Work Shift", "Final Exam", "Court Deadline", "Team Meeting"
- start_time / end_time: 24-hour HH:MM format; omit (or use null) if unknown
- all_day: true if no specific time, false if timed
- context: department, store number, course name, location, or any brief label; empty string if none
- Skip days off, non-events, and purely descriptive text
- Deduplicate: if the same date and event appears more than once, include it only once
- For academic calendars with "Key Dates" and per-session breakdown sections, extract only from the "Key Dates" sections
- Cap output at 60 events maximum
- Return ONLY valid JSON, no preamble, no markdown fences"""

USER_PROMPT_TEMPLATE = """Today's date is {today}.

Extract all calendar events from the document below.

{extracted_text}"""

MAX_INPUT_CHARS = 24_000


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    doc.close()
    return text


def _fmt_time(t: str) -> str:
    dt = datetime.datetime.strptime(t, "%H:%M")
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.strftime('%M')} {ampm}"


def parse_pdf_with_claude(pdf_bytes: bytes):
    text = extract_text_from_pdf(pdf_bytes)
    if not text or len(text.strip()) < 20:
        return [], ""
    if len(text) > MAX_INPUT_CHARS:
        raise ValueError("This document is too long to process. Please upload a shorter document.")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    today = datetime.date.today().isoformat()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_PROMPT_TEMPLATE.format(today=today, extracted_text=text)}]
    )
    usage = response.usage
    logger.info(f"Haiku usage: input={usage.input_tokens} output={usage.output_tokens}")
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    result = json.loads(raw)
    doc_type = result.get("document_type", "unknown")
    doc_title = result.get("document_title", "")
    confidence = result.get("confidence", "unknown")
    events = result.get("events", [])
    logger.info(f"Document: type={doc_type!r} title={doc_title!r} confidence={confidence} events={len(events)}")
    entries = []
    for ev in events:
        date_obj = datetime.date.fromisoformat(ev.get("date"))
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
        if doc_type == "work_schedule":
            event_title = "Work Shift"
        else:
            event_title = ev.get("title", "Event")
        context = ev.get("context", "")
        if " - " in context:
            context = context.split(" - ")[0].strip()
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
    return entries, doc_title
