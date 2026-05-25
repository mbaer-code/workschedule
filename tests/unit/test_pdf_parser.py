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
    _is_valid_date,
    _is_valid_time,
    _is_meaningful_title,
    _validate_events,
)


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

    def test_no_meaningful_title_rejected(self):
        events = [{
            "shift_date": "Mon, Sep 08",
            "shift_start": "",
            "shift_end": "",
            "department": "",
            "store_number": ""
        }]
        result = _validate_events(events, self._ctx())
        assert len(result) == 0

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
    "summary": "Home Depot work schedule for September 2025",
    "year": "2025",
    "subject": "Home Depot",
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
    def test_api_failure_returns_empty(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.side_effect = Exception("API timeout")
        result = parse_document("Sep 11 11:30 AM - 8:00 PM")
        assert result == []

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


class TestGetDocumentSummary:

    @patch('workschedule.services.pdf_parser._client')
    def test_summary_with_subject_and_location(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        client.messages.create.return_value = _mock_response(json.dumps(MOCK_CONTEXT))
        summary = get_document_summary("some pdf text")
        assert "Home Depot" in summary
        assert "0660" in summary

    @patch('workschedule.services.pdf_parser._client')
    def test_summary_without_extras(self, mock_client):
        client = MagicMock()
        mock_client.return_value = client
        ctx = {**MOCK_CONTEXT, "subject": None, "location": None}
        client.messages.create.return_value = _mock_response(json.dumps(ctx))
        summary = get_document_summary("some pdf text")
        assert "Home Depot work schedule" in summary
        assert "(" not in summary


# ---------------------------------------------------------------------------
# Live integration test (only runs with LIVE_TEST=1 in environment)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("LIVE_TEST"),
    reason="Set LIVE_TEST=1 to run live API tests"
)
class TestLiveIntegration:

    SAMPLE_SCHEDULE = """
    Home Depot Work Schedule - Store 0660
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
