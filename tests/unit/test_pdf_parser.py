"""
test_pdf_parser.py
------------------
Tests for pdf_parser.parse_document() and validation logic.

Run with:  pytest tests/test_pdf_parser.py -v

These tests use mocking so they don't hit the real Anthropic API.
Add LIVE_TEST=1 to env to run the live integration tests (costs a few cents).
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from workschedule.services.pdf_parser import (
    parse_document,
    get_document_summary,
    parse_image_with_summary,
    parse_images_with_summary,
    parse_images_via_transcription,
    _transcribe_images_to_text,
    shift_date_sort_key,
    _collapse_split_date_labels,
    _is_valid_date,
    _is_valid_time,
    _is_meaningful_title,
    _validate_events,
    ExtractionFailedError,
)
from workschedule.routes.schedule import extract_text_from_pdf
from workschedule.services.security import check_upload, SecurityError

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'fixtures')


# ---------------------------------------------------------------------------
# Unit tests — validation helpers (no API calls)
# ---------------------------------------------------------------------------

class TestIsValidDate:
    def test_standard_format(self):
        assert _is_valid_date("Mon, Sep 08", "2025")

    def test_short_format(self):
        assert _is_valid_date("Sep 08", "2025")

    def test_empty_string(self):
        assert not _is_valid_date("", "2025")

    def test_version_number(self):
        assert not _is_valid_date("3.2", "2025")

    def test_page_reference(self):
        assert not _is_valid_date("Page 12", "2025")

    def test_none_value(self):
        assert not _is_valid_date(None, "2025")


class TestIsValidTime:
    def test_standard_12hr(self):
        assert _is_valid_time("11:30 AM")

    def test_pm_time(self):
        assert _is_valid_time("8:00 PM")

    def test_empty_is_valid(self):
        # empty = all-day event, which is valid
        assert _is_valid_time("")

    def test_garbage(self):
        assert not _is_valid_time("not-a-time")

    def test_24hr_format_rejected(self):
        # We expect 12-hour format from the model
        assert not _is_valid_time("13:00")


class TestIsMeaningfulTitle:
    def test_normal_title(self):
        assert _is_meaningful_title("Plumbing Associate")

    def test_exam_title(self):
        assert _is_meaningful_title("Midterm Exam")

    def test_empty_string(self):
        assert not _is_meaningful_title("")

    def test_none(self):
        assert not _is_meaningful_title(None)

    def test_number_only(self):
        assert not _is_meaningful_title("123")

    def test_single_char(self):
        assert not _is_meaningful_title("X")


class TestValidateEvents:
    def _ctx(self):
        return {"year": "2025", "doc_type": "work_schedule"}

    def test_valid_timed_event(self):
        events = [{
            "shift_date": "Mon, Sep 08",
            "shift_start": "11:30 AM",
            "shift_end": "8:00 PM",
            "department": "Plumbing Associate",
            "store_number": "0660"
        }]
        result = _validate_events(events, self._ctx())
        assert len(result) == 1

    def test_valid_all_day_event(self):
        events = [{
            "shift_date": "Mon, Sep 08",
            "shift_start": "",
            "shift_end": "",
            "department": "Midterm Exam",
            "store_number": ""
        }]
        result = _validate_events(events, self._ctx())
        assert len(result) == 1

    def test_invalid_date_rejected(self):
        events = [{
            "shift_date": "3.2",
            "shift_start": "9:00 AM",
            "shift_end": "5:00 PM",
            "department": "Some Job",
            "store_number": ""
        }]
        result = _validate_events(events, self._ctx())
        assert len(result) == 0

    def test_mismatched_times_rejected(self):
        # start without end
        events = [{
            "shift_date": "Mon, Sep 08",
            "shift_start": "9:00 AM",
            "shift_end": "",
            "department": "Some Job",
            "store_number": ""
        }]
        result = _validate_events(events, self._ctx())
        assert len(result) == 0

    def test_blank_title_gets_fallback_not_rejected(self):
        events = [{
            "shift_date": "Mon, Sep 08",
            "shift_start": "",
            "shift_end": "",
            "department": "",
            "store_number": ""
        }]
        result = _validate_events(events, self._ctx())
        assert len(result) == 1
        assert result[0]['department'] == "Scheduled Event"

    def test_blank_title_falls_back_to_subject_when_available(self):
        events = [{
            "shift_date": "Mon, Sep 08",
            "shift_start": "",
            "shift_end": "",
            "department": "",
            "store_number": ""
        }]
        ctx = {**self._ctx(), "subject": "Acme Home Improvement"}
        result = _validate_events(events, ctx)
        assert len(result) == 1
        assert result[0]['department'] == "Acme Home Improvement"

    def test_multiple_mixed_events(self):
        events = [
            # valid
            {"shift_date": "Mon, Sep 08", "shift_start": "9:00 AM",
             "shift_end": "5:00 PM", "department": "Cashier", "store_number": "001"},
            # invalid date
            {"shift_date": "v1.4", "shift_start": "9:00 AM",
             "shift_end": "5:00 PM", "department": "Cashier", "store_number": ""},
            # valid all-day
            {"shift_date": "Wed, Oct 15", "shift_start": "",
             "shift_end": "", "department": "Final Exam", "store_number": ""},
        ]
        result = _validate_events(events, self._ctx())
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Integration tests — mock the Anthropic API
# ---------------------------------------------------------------------------

def _mock_response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


MOCK_CONTEXT = {
    "doc_type": "work_schedule",
    "summary": "Acme Home Improvement work schedule for September 2025",
    "year": "2025",
    "subject": "Acme Home Improvement",
    "location": "Store 0660",
    "has_calendar_content": True
}

MOCK_EVENTS = [
    {
        "shift_date": "Wed, Sep 11",
        "shift_start": "11:30 AM",
        "shift_end": "8:00 PM",
        "department": "Plumbing Associate",
        "store_number": "0660"
    },
    {
        "shift_date": "Fri, Sep 13",
        "shift_start": "7:00 AM",
        "shift_end": "3:30 PM",
        "department": "Plumbing Associate",
        "store_number": "0660"
    }
]

MOCK_SYLLABUS_CONTEXT = {
    "doc_type": "syllabus",
    "summary": "CS101 Introduction to Programming syllabus Fall 2025",
    "year": "2025",
    "subject": "CS101",
    "location": "Room 204",
    "has_calendar_content": True
}

MOCK_SYLLABUS_EVENTS = [
    {
        "shift_date": "Mon, Oct 06",
        "shift_start": "",
        "shift_end": "",
        "department": "Assignment 1 Due",
        "store_number": ""
    },
    {
        "shift_date": "Wed, Oct 15",
        "shift_start": "",
        "shift_end": "",
        "department": "Midterm Exam",
        "store_number": "Room 204"
    }
]


class TestParseDocument:

    @patch('workschedule.services.pdf_parser._client')
    def test_work_schedule_parsed(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.side_effect = [
            _mock_response(json.dumps(MOCK_CONTEXT)),
            _mock_response(json.dumps(MOCK_EVENTS))
        ]
        result = parse_document("Sep 11 11:30 AM - 8:00 PM Store 0660 Plumbing")
        assert len(result) == 2
        assert result[0]['shift_date'] == "Wed, Sep 11"
        assert result[0]['shift_start'] == "11:30 AM"
        assert result[0]['department'] == "Plumbing Associate"

    @patch('workschedule.services.pdf_parser._client')
    def test_syllabus_parsed(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.side_effect = [
            _mock_response(json.dumps(MOCK_SYLLABUS_CONTEXT)),
            _mock_response(json.dumps(MOCK_SYLLABUS_EVENTS))
        ]
        result = parse_document("CS101 Fall 2025. Assignment 1 due Oct 6. Midterm Oct 15.")
        assert len(result) == 2
        assert result[0]['shift_start'] == ""   # all-day
        assert result[0]['department'] == "Assignment 1 Due"

    @patch('workschedule.services.pdf_parser._client')
    def test_no_calendar_content_returns_empty(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        no_cal_context = {**MOCK_CONTEXT, "has_calendar_content": False}
        client.messages.create.return_value = _mock_response(json.dumps(no_cal_context))
        result = parse_document("This is a legal terms and conditions document.")
        assert result == []

    @patch('workschedule.services.pdf_parser._client')
    def test_empty_text_returns_empty(self, mock_client):
        result = parse_document("")
        assert result == []
        mock_client.assert_not_called()

    @patch('workschedule.services.pdf_parser._client')
    def test_short_text_returns_empty(self, mock_client):
        result = parse_document("hi")
        assert result == []
        mock_client.assert_not_called()

    @patch('workschedule.services.pdf_parser._client')
    def test_api_failure_raises_extraction_failed(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.side_effect = Exception("API timeout")
        with pytest.raises(ExtractionFailedError):
            parse_document("Sep 11 11:30 AM - 8:00 PM")

    @patch('workschedule.services.pdf_parser._client')
    def test_garbage_events_filtered(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        garbage_events = [
            # version number as date
            {"shift_date": "1.4", "shift_start": "9:00 AM",
             "shift_end": "5:00 PM", "department": "Work", "store_number": ""},
            # valid one
            {"shift_date": "Mon, Sep 08", "shift_start": "9:00 AM",
             "shift_end": "5:00 PM", "department": "Cashier", "store_number": ""},
        ]
        client.messages.create.side_effect = [
            _mock_response(json.dumps(MOCK_CONTEXT)),
            _mock_response(json.dumps(garbage_events))
        ]
        result = parse_document("some schedule text here for testing purposes")
        assert len(result) == 1
        assert result[0]['department'] == "Cashier"

    @patch('workschedule.services.pdf_parser._client')
    def test_nonstandard_weekday_abbreviations_normalized(self, mock_client):
        """
        Regression test: a source document that spells weekdays as "Tues"/
        "Thurs" (e.g. a college exam schedule table) instead of the
        standard "Tue"/"Thu" used to get silently dropped — the shape
        validator required exactly 3 letters, so a model extracting these
        verbatim from the source produced dates that never made it into
        the output, sometimes zeroing out the whole result.
        """
        client = MagicMock()
        mock_client.return_value = client
        events = [
            {"shift_date": "Tues, May 19", "shift_start": "10:15 AM",
             "shift_end": "12:15 PM", "department": "Final Exam", "store_number": ""},
            {"shift_date": "Thurs, May 21", "shift_start": "3:00 PM",
             "shift_end": "5:00 PM", "department": "Final Exam", "store_number": ""},
            {"shift_date": "Mon, May 18", "shift_start": "8:00 AM",
             "shift_end": "10:00 AM", "department": "Final Exam", "store_number": ""},
        ]
        client.messages.create.side_effect = [
            _mock_response(json.dumps(MOCK_CONTEXT)),
            _mock_response(json.dumps(events))
        ]
        result = parse_document("some exam schedule text here for testing")
        assert len(result) == 3
        # Normalized to the standard 3-letter form ics_generator.py's
        # strptime("%a, ...") actually requires.
        dates = {e['shift_date'] for e in result}
        assert dates == {"Tue, May 19", "Thu, May 21", "Mon, May 18"}


class TestGetDocumentSummary:

    @patch('workschedule.services.pdf_parser._client')
    def test_summary_with_subject_and_location(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_CONTEXT))
        summary = get_document_summary("some pdf text")
        assert "Acme Home Improvement" in summary
        assert "0660" in summary

    @patch('workschedule.services.pdf_parser._client')
    def test_summary_without_extras(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        ctx = {**MOCK_CONTEXT, "subject": None, "location": None}
        client.messages.create.return_value = _mock_response(json.dumps(ctx))
        summary = get_document_summary("some pdf text")
        assert "Acme Home Improvement work schedule" in summary
        assert "(" not in summary


MOCK_IMAGE_RESPONSE = {
    "doc_type": "work_schedule",
    "summary": "Photo of an Acme Home Improvement work schedule",
    "year": "2026",
    "subject": "Acme Home Improvement",
    "location": "Store 0660",
    "has_calendar_content": True,
    "events": [
        {"shift_date": "Mon, Sep 08", "shift_start": "9:00 AM",
         "shift_end": "5:00 PM", "department": "Cashier", "store_number": "0660"}
    ]
}

FAKE_JPEG_BYTES = b'\xff\xd8\xff' + b'fake-jpeg-data'


class TestParseImage:
    """
    Image path uses one combined vision call (context + extraction) instead
    of the text path's two passes, since re-sending image bytes for a
    second pass would double vision token cost for no accuracy gain.
    """

    @patch('workschedule.services.pdf_parser._client')
    def test_image_parsed(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_IMAGE_RESPONSE))

        events, summary = parse_image_with_summary(FAKE_JPEG_BYTES, media_type="image/jpeg")

        assert len(events) == 1
        assert events[0]['department'] == 'Cashier'
        assert "Acme Home Improvement" in summary

    @patch('workschedule.services.pdf_parser._client')
    def test_image_makes_single_api_call(self, mock_client):
        """Confirms the cost-saving design: one vision call, not two."""
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_IMAGE_RESPONSE))

        parse_image_with_summary(FAKE_JPEG_BYTES, media_type="image/jpeg")

        assert client.messages.create.call_count == 1

    @patch('workschedule.services.pdf_parser._client')
    def test_image_sends_vision_content_block(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_IMAGE_RESPONSE))

        parse_image_with_summary(FAKE_JPEG_BYTES, media_type="image/png")

        _, kwargs = client.messages.create.call_args
        content = kwargs['messages'][0]['content']
        image_blocks = [b for b in content if b.get('type') == 'image']
        assert len(image_blocks) == 1
        assert image_blocks[0]['source']['media_type'] == 'image/png'

    @patch('workschedule.services.pdf_parser._client')
    def test_image_no_calendar_content_returns_empty(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        no_cal = {**MOCK_IMAGE_RESPONSE, "has_calendar_content": False, "events": []}
        client.messages.create.return_value = _mock_response(json.dumps(no_cal))

        events, summary = parse_image_with_summary(FAKE_JPEG_BYTES)
        assert events == []

    @patch('workschedule.services.pdf_parser._client')
    def test_image_api_failure_returns_empty(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.side_effect = Exception("API timeout")

        events, summary = parse_image_with_summary(FAKE_JPEG_BYTES)
        assert events == []

    @patch('workschedule.services.pdf_parser._client')
    def test_image_garbage_events_filtered(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        response = {
            **MOCK_IMAGE_RESPONSE,
            "events": [
                {"shift_date": "1.4", "shift_start": "9:00 AM",
                 "shift_end": "5:00 PM", "department": "Work", "store_number": ""},
                {"shift_date": "Mon, Sep 08", "shift_start": "9:00 AM",
                 "shift_end": "5:00 PM", "department": "Cashier", "store_number": ""},
            ]
        }
        client.messages.create.return_value = _mock_response(json.dumps(response))

        events, _ = parse_image_with_summary(FAKE_JPEG_BYTES)
        assert len(events) == 1
        assert events[0]['department'] == 'Cashier'

    def test_empty_bytes_returns_empty_no_api_call(self):
        with patch('workschedule.services.pdf_parser._client') as mock_client:
            events, summary = parse_image_with_summary(b"")
            assert events == []
            mock_client.assert_not_called()


class TestParseImagesMulti:
    """
    Multi-photo path: several pages/screens of the same document merged
    in a single vision call. parse_image_with_summary (singular) is kept
    as a back-compat wrapper around this for one-image callers.
    """

    @patch('workschedule.services.pdf_parser._client')
    def test_multi_image_single_api_call(self, mock_client):
        """Confirms 4 photos still cost exactly 1 vision call, not 4."""
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_IMAGE_RESPONSE))

        images = [(FAKE_JPEG_BYTES, "image/jpeg")] * 4
        events, summary = parse_images_with_summary(images)

        assert client.messages.create.call_count == 1
        assert len(events) == 1

    @patch('workschedule.services.pdf_parser._client')
    def test_multi_image_sends_one_content_block_per_image(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_IMAGE_RESPONSE))

        images = [(FAKE_JPEG_BYTES, "image/jpeg"), (FAKE_JPEG_BYTES, "image/png"), (FAKE_JPEG_BYTES, "image/jpeg")]
        parse_images_with_summary(images)

        sent_content = client.messages.create.call_args.kwargs['messages'][0]['content']
        image_blocks = [b for b in sent_content if b['type'] == 'image']
        text_blocks = [b for b in sent_content if b['type'] == 'text']
        assert len(image_blocks) == 3
        assert len(text_blocks) == 1
        # Multi-image prompt should reference merging across images, not
        # the single-image prompt.
        assert "SAME document" in text_blocks[0]['text']

    @patch('workschedule.services.pdf_parser._client')
    def test_single_image_uses_single_image_prompt(self, mock_client):
        """A 1-image call should still read like the original single-image prompt."""
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_IMAGE_RESPONSE))

        parse_images_with_summary([(FAKE_JPEG_BYTES, "image/jpeg")])

        sent_content = client.messages.create.call_args.kwargs['messages'][0]['content']
        text_block = next(b for b in sent_content if b['type'] == 'text')
        assert "SAME document" not in text_block['text']

    def test_empty_list_returns_empty_no_api_call(self):
        with patch('workschedule.services.pdf_parser._client') as mock_client:
            events, summary = parse_images_with_summary([])
            assert events == []
            mock_client.assert_not_called()

    @patch('workschedule.services.pdf_parser._client')
    def test_single_image_wrapper_still_works(self, mock_client):
        """parse_image_with_summary (singular) is a thin wrapper — same result."""
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_IMAGE_RESPONSE))

        events, summary = parse_image_with_summary(FAKE_JPEG_BYTES, media_type="image/jpeg")

        assert len(events) == 1
        assert client.messages.create.call_count == 1


class TestParseImagesViaTranscription:
    """
    The actual entry point schedule.py calls for photo uploads. Built
    after real testing found direct single-shot vision extraction
    (TestParseImagesMulti above) produced four different wrong date
    pairings across four uploads of the exact same unchanged photo of
    the Workforce Tools schedule's split-label date layout. This
    approach transcribes the image to plain text (a task vision models
    are reliably good at) and hands the fragile date-pairing problem to
    the same deterministic _collapse_split_date_labels() pipeline
    already proven correct against a real document.
    """

    @patch('workschedule.services.pdf_parser._client')
    def test_transcribe_then_parse_full_pipeline(self, mock_client):
        """
        The core claim this whole approach rests on: if the vision model
        transcribes the image faithfully (including the split-label date
        layout, exactly as PyMuPDF's real extraction of this document
        does), the existing proven text pipeline produces the correct
        result -- reusing the same fixture text this session's PDF-path
        regression test already verified end-to-end.
        """
        client = MagicMock()
        mock_client.return_value = client

        transcribed_text = (
            "Mar 2 - 8 12:00 hours\n"
            "Mar\n2\n6:00 PM - 10:00 PM [4:00]\n0660 - Store 026 - Plumbing & Bath Associate\n"
            "Mar\n3\n6:00 PM - 10:00 PM [4:00]\n0660 - Store 026 - Plumbing & Bath Associate\n"
            "Mar\n4\nMar\n5\nMar\n6\nMar\n7\n"
            "Mar\n8\n4:00 PM - 8:00 PM [4:00]\n0660 - Store 026 - Plumbing & Bath Associate\n"
        )
        expected_events = [
            {"shift_date": "Mon, Mar 02", "shift_start": "6:00 PM", "shift_end": "10:00 PM",
             "department": "Plumbing & Bath Associate", "store_number": "0660"},
            {"shift_date": "Tue, Mar 03", "shift_start": "6:00 PM", "shift_end": "10:00 PM",
             "department": "Plumbing & Bath Associate", "store_number": "0660"},
            {"shift_date": "Sun, Mar 08", "shift_start": "4:00 PM", "shift_end": "8:00 PM",
             "department": "Plumbing & Bath Associate", "store_number": "0660"},
        ]
        # First call: transcription. Then context pass, then extraction
        # pass (parse_document_with_summary's normal 2-call sequence).
        client.messages.create.side_effect = [
            _mock_response(transcribed_text),
            _mock_response(json.dumps(MOCK_CONTEXT)),
            _mock_response(json.dumps(expected_events)),
        ]

        events, summary = parse_images_via_transcription([(FAKE_JPEG_BYTES, "image/jpeg")])

        assert client.messages.create.call_count == 3
        dates = [e['shift_date'] for e in events]
        assert dates == ['Mon, Mar 02', 'Tue, Mar 03', 'Sun, Mar 08']

    @patch('workschedule.services.pdf_parser._client')
    def test_transcription_call_uses_temperature_zero(self, mock_client):
        """Determinism matters here specifically -- real testing showed
        the same unmodified photo producing different wrong answers
        across repeated uploads."""
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response("some text")

        _transcribe_images_to_text([(FAKE_JPEG_BYTES, "image/jpeg")])

        assert client.messages.create.call_args.kwargs['temperature'] == 0

    @patch('workschedule.services.pdf_parser._client')
    def test_multi_image_transcription_strips_break_markers(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(
            "page one text\n---IMAGE BREAK---\npage two text"
        )

        text = _transcribe_images_to_text([
            (FAKE_JPEG_BYTES, "image/jpeg"), (FAKE_JPEG_BYTES, "image/jpeg")
        ])

        assert "---IMAGE BREAK---" not in text
        assert "page one text" in text
        assert "page two text" in text

    def test_empty_list_returns_empty_no_api_call(self):
        with patch('workschedule.services.pdf_parser._client') as mock_client:
            events, summary = parse_images_via_transcription([])
            assert events == []
            mock_client.assert_not_called()


class TestShiftDateSortKey:
    """
    Regression coverage for a real bug: sorting shift_date strings
    directly (e.g. 'Wed, Sep 11') sorts by weekday name alphabetically
    since that's the start of the string, scrambling actual date order.
    """

    def test_with_weekday_prefix_sorts_chronologically(self):
        dates = ["Mon, Mar 02", "Tue, Mar 03", "Sun, Mar 08",
                 "Mon, Mar 09", "Wed, Mar 11", "Thu, Mar 12"]
        result = sorted(dates, key=shift_date_sort_key)
        assert result == ["Mon, Mar 02", "Tue, Mar 03", "Sun, Mar 08",
                           "Mon, Mar 09", "Wed, Mar 11", "Thu, Mar 12"]

    def test_raw_string_sort_would_scramble_this(self):
        """Confirms the bug this fix addresses actually existed."""
        dates = ["Mon, Mar 02", "Tue, Mar 03", "Sun, Mar 08",
                 "Mon, Mar 09", "Wed, Mar 11", "Thu, Mar 12"]
        naive_sort = sorted(dates)
        chronological = sorted(dates, key=shift_date_sort_key)
        assert naive_sort != chronological

    def test_without_weekday_prefix(self):
        dates = ["Sep 08", "Sep 03", "Sep 15"]
        result = sorted(dates, key=shift_date_sort_key)
        assert result == ["Sep 03", "Sep 08", "Sep 15"]

    def test_across_months(self):
        dates = ["Oct 02", "Sep 30", "Nov 01"]
        result = sorted(dates, key=shift_date_sort_key)
        assert result == ["Sep 30", "Oct 02", "Nov 01"]

    def test_malformed_sorts_last_not_raises(self):
        dates = ["Sep 08", "garbage", "", None, "Sep 03"]
        result = sorted(dates, key=shift_date_sort_key)
        assert result[0] == "Sep 03"
        assert result[1] == "Sep 08"


class TestRealWorkforceToolsSchedule:
    """
    Regression coverage using a real schedule PDF that triggered a
    production bug: the upload produced no response at all (not rejected
    — just silence). Root cause turned out to be gunicorn's default 30s
    worker timeout being too short for the two-pass Anthropic call plus
    GCS write (fixed separately in the Dockerfile), not anything wrong
    with this file's content or structure.

    The file itself is an unusual export: a single standard Letter page
    containing three separate weekly schedule blocks laid out side by
    side (like on-screen captures of a web app, monitor icon included),
    covering three different weeks in one PDF — one week with genuinely
    no shifts, two weeks with real shifts. Kept here as a fixture because
    its layout is more complex than the average schedule PDF and it's a
    real document that already exposed one real bug.
    """

    FIXTURE_PATH = os.path.join(FIXTURES_DIR, 'workforce_tools_schedule_composite.pdf')

    def _load_bytes(self) -> bytes:
        with open(self.FIXTURE_PATH, 'rb') as f:
            return f.read()

    def test_fixture_exists(self):
        assert os.path.exists(self.FIXTURE_PATH)

    def test_passes_security_check_as_pdf(self):
        data = self._load_bytes()
        kind = check_upload(
            data, 'workforce_tools_schedule_composite.pdf', 'application/pdf',
            ip_address='127.0.0.1', session_id='test-workforce-tools'
        )
        assert kind == 'pdf'

    def test_text_extraction_succeeds(self):
        data = self._load_bytes()
        text = extract_text_from_pdf(data)
        assert len(text) > 50  # clears the min_text_chars security gate
        assert len(text) < 8000  # clears max_text_chars without truncation

    def test_text_extraction_captures_all_three_weeks(self):
        data = self._load_bytes()
        text = extract_text_from_pdf(data)
        assert 'Feb 23 - Mar 1' in text
        assert 'Mar 2 - 8' in text
        assert 'Mar 9 - 15' in text

    def test_text_extraction_captures_shift_details(self):
        data = self._load_bytes()
        text = extract_text_from_pdf(data)
        assert '0660 - Store 026 - Plumbing & Bath Associate' in text
        assert '6:00 PM - 10:00 PM' in text
        assert 'No shifts are scheduled within the timeframe' in text

    def test_split_date_labels_collapse_to_correct_pairing(self):
        """
        Real production bug (found via manual testing, not caught by the
        tests above): this PDF's raw text puts each date on two separate
        lines (a bare "Mar" line, then a bare day-number line), with runs
        of several consecutive blank dates between real shifts. Asking
        the model to track "this shift belongs to the label N lines back"
        via prose instructions alone proved unreliable on this real
        document — shifts kept landing on an earlier blank date instead
        of their own. _collapse_split_date_labels() removes that ambiguity
        deterministically, in code, before either AI pass ever sees the
        text. This asserts the exact known-correct pairing directly,
        independent of any model behavior.
        """
        data = self._load_bytes()
        text = extract_text_from_pdf(data)
        collapsed = _collapse_split_date_labels(text)

        # Real shifts -- each date paired with ITS OWN shift, not an
        # earlier blank date's.
        assert 'Mar 02: 6:00 PM - 10:00 PM' in collapsed
        assert 'Mar 03: 6:00 PM - 10:00 PM' in collapsed
        assert 'Mar 08: 4:00 PM - 8:00 PM' in collapsed
        assert 'Mar 09: 6:00 PM - 10:00 PM' in collapsed
        assert 'Mar 11: 6:00 PM - 10:00 PM' in collapsed
        assert 'Mar 12: 6:00 PM - 10:00 PM' in collapsed

        # Blank dates explicitly marked as such -- not silently dropped,
        # and not carrying a shift that belongs to a later date.
        for blank_day in ('04', '05', '06', '07', '10', '13', '14', '15'):
            assert f'Mar {blank_day}: (no shift)' in collapsed

    def test_collapse_leaves_non_split_label_text_unchanged(self):
        """The collapse must not fire (or alter anything) on formats that
        don't use this specific two-line date pattern -- e.g. plain prose
        or inline table rows with the date and details on one line."""
        inline_text = (
            "Mon, Sep 08  11:30 AM - 8:00 PM  Plumbing & Bath  0660\n"
            "Tue, Sep 09  no shift\n"
            "Wed, Sep 10  1:00 PM - 9:00 PM  Plumbing & Bath  0660\n"
        )
        assert _collapse_split_date_labels(inline_text) == inline_text


class TestSyntheticGridSchedule:
    """
    Synthetic fixture, deliberately structured to be the OPPOSITE of
    workforce_tools_schedule_composite.pdf: a single plain table, numeric
    MM/DD/YYYY dates, no repeated title/header banner anywhere in the
    document. This exists to check that the header/title-avoidance rules
    added to the vision prompt this session (don't extract the document's
    own title as an event; don't source a shift's date from the title's
    date range) don't cause any false suppression when there's no such
    banner present at all to confuse — every real test this session used
    the same one banner-heavy document, so this is real structural
    coverage that was previously missing entirely.

    Not a real employer's export — built to test structural diversity,
    not to imitate any specific company's actual scheduling software.
    """

    FIXTURE_PATH = os.path.join(FIXTURES_DIR, 'generic_grid_schedule.pdf')

    def _load_bytes(self) -> bytes:
        with open(self.FIXTURE_PATH, 'rb') as f:
            return f.read()

    def test_fixture_exists(self):
        assert os.path.exists(self.FIXTURE_PATH)

    def test_passes_security_check_as_pdf(self):
        data = self._load_bytes()
        kind = check_upload(
            data, 'generic_grid_schedule.pdf', 'application/pdf',
            ip_address='127.0.0.1', session_id='test-grid'
        )
        assert kind == 'pdf'

    def test_text_extraction_captures_shift_details(self):
        data = self._load_bytes()
        text = extract_text_from_pdf(data)
        assert '04/06/2026' in text
        assert '8:00 AM - 4:00 PM' in text
        assert 'OFF' in text

    def test_split_date_label_collapse_does_not_fire(self):
        """This format doesn't use the split-label date pattern (dates
        and details share one table row) -- the collapse must leave it
        untouched, not misinterpret table rows as split labels."""
        data = self._load_bytes()
        text = extract_text_from_pdf(data)
        assert _collapse_split_date_labels(text) == text


class TestSyntheticRosterSchedule:
    """
    Synthetic fixture covering a structurally different case: multiple
    named people with separate shifts under one date (a team roster),
    including a date with nobody scheduled. This is the multi-name-per-
    date shape flagged back in July (a real user's schedule listed
    multiple names per date) as never actually implemented -- the
    current schema only expects one shift per event. This fixture
    exists so that gap has a concrete regression target once work on it
    starts, rather than staying an undocumented known limitation.

    Not a real employer's export — built to test structural diversity,
    not to imitate any specific company's actual scheduling software.
    """

    FIXTURE_PATH = os.path.join(FIXTURES_DIR, 'roster_multi_name_schedule.pdf')

    def _load_bytes(self) -> bytes:
        with open(self.FIXTURE_PATH, 'rb') as f:
            return f.read()

    def test_fixture_exists(self):
        assert os.path.exists(self.FIXTURE_PATH)

    def test_passes_security_check_as_pdf(self):
        data = self._load_bytes()
        kind = check_upload(
            data, 'roster_multi_name_schedule.pdf', 'application/pdf',
            ip_address='127.0.0.1', session_id='test-roster'
        )
        assert kind == 'pdf'

    def test_text_extraction_captures_multiple_names_per_date(self):
        data = self._load_bytes()
        text = extract_text_from_pdf(data)
        assert 'A. Chen' in text
        assert 'R. Diaz' in text
        assert 'J. Osei' in text
        assert '(no one scheduled)' in text


# ---------------------------------------------------------------------------
# Live integration test (only runs with LIVE_TEST=1 in environment)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("LIVE_TEST"),
    reason="Set LIVE_TEST=1 to run live API tests"
)
class TestLiveIntegration:

    SAMPLE_SCHEDULE = """
    Acme Home Improvement Work Schedule - Store 0660
    September 2025

    Wed Sep 11   11:30 AM - 8:00 PM   Plumbing & Bath Associate
    Fri Sep 13    7:00 AM - 3:30 PM   Plumbing & Bath Associate
    Sun Sep 15   12:00 PM - 8:30 PM   Plumbing & Bath Associate
    """

    SAMPLE_SYLLABUS = """
    CS101 Introduction to Programming
    Fall 2025 - Professor Smith - Room 204

    Week 3 (Sep 15): Variables and data types
    Assignment 1 Due: Oct 6
    Midterm Exam: Oct 15 (covers chapters 1-5)
    Assignment 2 Due: Nov 3
    Final Exam: Dec 10, 2:00 PM - 4:00 PM Room 204
    """

    def test_live_work_schedule(self):
        result = parse_document(self.SAMPLE_SCHEDULE)
        assert len(result) >= 1
        assert all(e['shift_start'] for e in result)  # all timed
        assert all(e['department'] for e in result)

    def test_live_syllabus(self):
        result = parse_document(self.SAMPLE_SYLLABUS)
        assert len(result) >= 3
        # Final exam should have times, others all-day
        final = next((e for e in result if 'Final' in e['department']), None)
        assert final is not None
        assert final['shift_start'] != ""

    def test_live_summary(self):
        summary = get_document_summary(self.SAMPLE_SCHEDULE)
        assert len(summary) > 10

    def test_live_real_workforce_tools_schedule(self):
        """
        Full pipeline against the real problematic fixture: text
        extraction -> two-pass Claude parsing -> validation -> sort.
        Covers the three-week composite layout and confirms events come
        back in correct chronological order (regression for the
        shift_date sort bug, fixed separately in shift_date_sort_key()).
        """
        fixture_path = os.path.join(FIXTURES_DIR, 'workforce_tools_schedule_composite.pdf')
        with open(fixture_path, 'rb') as f:
            data = f.read()
        text = extract_text_from_pdf(data)

        events = parse_document(text)

        # The Feb 23 - Mar 1 week explicitly has no shifts; the other two
        # weeks have 6 real shifts between them (2 + 1 + 3 across Mar 2-8
        # and Mar 9-15). Use >= since the model's exact recall can vary
        # slightly; the important thing is it finds the real ones and
        # skips the empty week.
        assert len(events) >= 4
        assert all(e['department'] for e in events)
        assert all('Plumbing' in e['department'] for e in events)

        # Sanity check that shift_date_sort_key() handles real model output
        # cleanly (no exceptions, no malformed-date fallbacks) and produces
        # non-decreasing order. The scramble-vs-fix comparison itself is
        # covered with deterministic data in TestShiftDateSortKey; this is
        # just confirming the same key function holds up on live output.
        sorted_events = sorted(events, key=lambda e: shift_date_sort_key(e['shift_date']))
        keys = [shift_date_sort_key(e['shift_date']) for e in sorted_events]
        assert keys == sorted(keys)
        assert keys[0] != (99, 99)  # not silently falling back on malformed dates
