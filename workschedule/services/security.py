"""
security.py
-----------
Security gate for the PDF upload pipeline.

Call check_upload() at the top of upload_pdf() before any processing.
Call check_text() after extract_text_from_pdf() before calling the AI.

All checks are fast and free — they run before any API call is made,
so a rejected upload costs nothing.

Usage:
    from workschedule.services.security import check_upload, check_text, SecurityError

    try:
        check_upload(file_bytes, filename, mimetype, ip_address, session_id)
        text = extract_text_from_pdf(file_bytes)
        check_text(text)
        events = parse_document(text)
    except SecurityError as e:
        return render_template("upload_schedule_new.html", pdf_error=str(e))
"""

import logging
import time
from collections import defaultdict
from threading import Lock

from workschedule.services.parser_limits import limits

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class SecurityError(Exception):
    """Raised when an upload fails a security check."""
    pass


# ---------------------------------------------------------------------------
# Simple in-process rate limiter
# (Good enough for Cloud Run single-instance; upgrade to Redis if you scale)
# ---------------------------------------------------------------------------

class _RateLimiter:
    def __init__(self):
        self._ip_log: dict[str, list] = defaultdict(list)
        self._session_log: dict[str, list] = defaultdict(list)
        self._lock = Lock()

    def _prune(self, timestamps: list, window_seconds: int) -> list:
        cutoff = time.time() - window_seconds
        return [t for t in timestamps if t > cutoff]

    def check_ip(self, ip: str):
        with self._lock:
            self._ip_log[ip] = self._prune(self._ip_log[ip], 3600)
            if len(self._ip_log[ip]) >= limits.max_uploads_per_ip_per_hour:
                logger.warning(f"[security] Rate limit hit for IP {ip}")
                raise SecurityError(
                    f"Too many uploads from your connection. "
                    f"Please try again in an hour."
                )
            self._ip_log[ip].append(time.time())

    def check_session(self, session_id: str):
        with self._lock:
            self._session_log[session_id] = self._prune(
                self._session_log[session_id], 86400)
            if len(self._session_log[session_id]) >= limits.max_uploads_per_session_per_day:
                logger.warning(f"[security] Daily session limit hit: {session_id}")
                raise SecurityError(
                    "You've reached the daily upload limit. "
                    "Please try again tomorrow."
                )
            self._session_log[session_id].append(time.time())


_rate_limiter = _RateLimiter()


# ---------------------------------------------------------------------------
# File-level checks
# ---------------------------------------------------------------------------

def _check_extension(filename: str):
    if not filename:
        raise SecurityError("No filename provided.")
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in limits.allowed_extensions):
        raise SecurityError("Only PDF files are accepted.")


def _check_mime(mimetype: str):
    if mimetype and mimetype.split(';')[0].strip() not in limits.allowed_mime_types:
        logger.warning(f"[security] Unexpected MIME type: {mimetype}")
        raise SecurityError("Only PDF files are accepted.")


def _check_magic_bytes(data: bytes):
    if not data or not data.startswith(limits.pdf_magic_bytes):
        logger.warning("[security] File failed magic bytes check — not a real PDF")
        raise SecurityError("The file does not appear to be a valid PDF.")


def _check_file_size(data: bytes):
    size = len(data)
    if size < limits.min_file_size_bytes:
        raise SecurityError("The file is too small to be a valid PDF.")
    if size > limits.max_file_size_bytes:
        mb = limits.max_file_size_bytes // (1024 * 1024)
        logger.warning(f"[security] File too large: {size} bytes")
        raise SecurityError(
            f"File is too large. Maximum size is {mb}MB. "
            f"Work schedule PDFs are typically under 1MB."
        )


# ---------------------------------------------------------------------------
# Text-level checks (after extraction, before AI call)
# ---------------------------------------------------------------------------

def _check_text_length(text: str):
    length = len(text.strip())
    if length < limits.min_text_chars:
        raise SecurityError(
            "Could not extract readable text from this PDF. "
            "If it's a scanned image, text extraction is not yet supported."
        )
    if length > limits.max_text_chars:
        logger.info(
            f"[security] Text truncated from {length} to {limits.max_text_chars} chars"
        )
        # Don't reject — just truncate. Logged so we can tune the limit if needed.


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_upload(
    file_bytes: bytes,
    filename: str,
    mimetype: str,
    ip_address: str = None,
    session_id: str = None,
):
    """
    Run all file-level security checks before any processing.
    Raises SecurityError with a user-friendly message if anything fails.
    """
    logger.info(f"[security] Checking upload: {filename}, "
                f"size={len(file_bytes)}, mime={mimetype}, ip={ip_address}")

    # Rate limits first — fastest check, no file reading needed
    if ip_address:
        _rate_limiter.check_ip(ip_address)
    if session_id:
        _rate_limiter.check_session(session_id)

    # File checks
    _check_extension(filename)
    _check_mime(mimetype)
    _check_file_size(file_bytes)
    _check_magic_bytes(file_bytes)

    logger.info(f"[security] Upload passed all checks: {filename}")


def check_text(text: str) -> str:
    """
    Run text-level checks after PDF extraction, before AI call.
    Returns truncated text if it exceeds the char limit.
    Raises SecurityError if text is too short.
    """
    _check_text_length(text)
    if len(text) > limits.max_text_chars:
        return text[:limits.max_text_chars]
    return text
