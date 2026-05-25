"""
parser_limits.py
----------------
Tunable limits for the PDF parser pipeline.

All values have sane defaults but can be overridden via environment variables
or Cloud Run config — no redeployment needed.

Hardcoded (security-critical, change only in code):
  - Allowed MIME types
  - Magic bytes signature
  - Allowed file extensions

Tunable via env vars (adjust in GCP console or .env):
  - Everything else
"""

import os
from dataclasses import dataclass, field


@dataclass
class ParserLimits:

    # ------------------------------------------------------------------
    # File checks
    # ------------------------------------------------------------------

    # Maximum upload size in bytes. A real schedule PDF is 50-500KB.
    # 5MB is generous enough for any legitimate document.
    max_file_size_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("MAX_FILE_SIZE_MB", "5")) * 1024 * 1024
    )

    # Minimum file size — anything smaller than this is probably not a real PDF.
    min_file_size_bytes: int = field(
        default_factory=lambda: int(os.getenv("MIN_FILE_SIZE_BYTES", "1024"))
    )

    # ------------------------------------------------------------------
    # Text / AI checks
    # ------------------------------------------------------------------

    # Maximum characters sent to the AI. Keeps cost bounded.
    # 8000 chars comfortably covers a multi-week work schedule.
    max_text_chars: int = field(
        default_factory=lambda: int(os.getenv("MAX_TEXT_CHARS", "8000"))
    )

    # Minimum extracted text length. Below this the PDF is likely
    # a scanned image (no OCR yet) or corrupt.
    min_text_chars: int = field(
        default_factory=lambda: int(os.getenv("MIN_TEXT_CHARS", "50"))
    )

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    # Max uploads per IP address per hour.
    max_uploads_per_ip_per_hour: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOADS_PER_IP_HOUR", "5"))
    )

    # Max uploads per session per day.
    max_uploads_per_session_per_day: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOADS_SESSION_DAY", "10"))
    )

    # ------------------------------------------------------------------
    # HARDCODED — do not expose as env vars (security-critical)
    # ------------------------------------------------------------------

    # Only PDF files accepted. Period.
    allowed_extensions: tuple = ('.pdf',)

    # MIME types we accept from the browser.
    allowed_mime_types: tuple = (
        'application/pdf',
        'application/x-pdf',
        'application/octet-stream',  # some browsers send this for PDFs
    )

    # First 4 bytes of every valid PDF file.
    # Cannot be faked by renaming a file or setting a MIME header.
    pdf_magic_bytes: bytes = b'%PDF'


# Singleton — import this everywhere rather than instantiating per request.
limits = ParserLimits()
