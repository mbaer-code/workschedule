"""
security.py
-----------
Security gate for the document upload pipeline (PDF or phone-photo image).

Call check_upload() at the top of upload_pdf() before any processing.
It returns the detected file kind ("pdf" or "image") so the caller can
branch to the right extraction path.

Call check_text() after extract_text_from_pdf() before calling the AI
(PDF path only — images skip straight to the vision call).

All checks are fast and free — they run before any API call is made,
so a rejected upload costs nothing.

Usage:
    from workschedule.services.security import check_upload, check_text, SecurityError

    try:
        kind = check_upload(file_bytes, filename, mimetype, ip_address, session_id)
        if kind == "pdf":
            text = extract_text_from_pdf(file_bytes)
            check_text(text)
            events = parse_document(text)
        else:
            events = parse_image(file_bytes)
    except SecurityError as e:
        return render_template("upload_schedule_new.html", pdf_error=str(e))
"""

import logging
import time
from collections import defaultdict
from io import BytesIO
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

_ACCEPT_MSG = "Only PDF files or PNG/JPEG photos are accepted."


def _check_extension(filename: str):
    if not filename:
        raise SecurityError("No filename provided.")
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in limits.allowed_extensions):
        raise SecurityError(_ACCEPT_MSG)


def _check_mime(mimetype: str):
    if mimetype and mimetype.split(';')[0].strip() not in limits.allowed_mime_types:
        logger.warning(f"[security] Unexpected MIME type: {mimetype}")
        raise SecurityError(_ACCEPT_MSG)


def _detect_kind(data: bytes) -> str:
    """
    Identify the real file type from its magic bytes — the only check that
    can't be faked by renaming a file or forging a MIME header.
    Returns "pdf" or "image". Raises SecurityError if neither matches.
    """
    if not data:
        raise SecurityError("The uploaded file is empty.")
    if data.startswith(limits.pdf_magic_bytes):
        return "pdf"
    if data.startswith(limits.png_magic_bytes):
        return "image"
    if data.startswith(limits.jpeg_magic_bytes):
        return "image"
    # HEIC/HEIF: bytes 4-8 are the "ftyp" box marker, bytes 8-12 are the brand.
    if len(data) >= 12 and data[4:8] == b'ftyp' and data[8:12] in limits.heic_ftyp_brands:
        return "image"
    logger.warning("[security] File failed magic bytes check — unrecognized format")
    raise SecurityError(
        "The file does not appear to be a valid PDF, PNG, or JPEG."
    )


def _check_file_size(data: bytes, kind: str):
    size = len(data)
    if kind == "image":
        if size < limits.min_image_size_bytes:
            raise SecurityError("The image is too small to be a legible schedule photo.")
        if size > limits.max_image_size_bytes:
            mb = limits.max_image_size_bytes // (1024 * 1024)
            logger.warning(f"[security] Image too large: {size} bytes")
            raise SecurityError(
                f"That photo is too large (over {mb}MB). Take a screenshot "
                f"of it and upload that instead."
            )
    else:
        if size < limits.min_file_size_bytes:
            raise SecurityError("The file is too small to be a valid PDF.")
        if size > limits.max_file_size_bytes:
            mb = limits.max_file_size_bytes // (1024 * 1024)
            logger.warning(f"[security] File too large: {size} bytes")
            raise SecurityError(
                f"File is too large. Maximum size is {mb}MB. "
                f"Work schedule PDFs are typically under 1MB."
            )


def _check_image_dimensions(data: bytes):
    """
    Guard against decompression-bomb images: a small file on disk that
    decodes to an enormous bitmap and exhausts memory/CPU. PIL's Image.open()
    only reads the header here — it does not decode pixel data — so this is
    cheap even for a maliciously crafted file.
    """
    try:
        from PIL import Image
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        logger.error("[security] Pillow not installed — cannot validate image dimensions")
        raise SecurityError("Image validation is temporarily unavailable. Please try a PDF instead.")

    try:
        with Image.open(BytesIO(data)) as img:
            width, height = img.size
    except Exception as e:
        logger.warning(f"[security] Could not read image header: {e}")
        raise SecurityError("The image file appears to be corrupted.")

    pixels = width * height
    if pixels > limits.max_image_pixels:
        logger.warning(f"[security] Image dimensions too large: {width}x{height} = {pixels} px")
        raise SecurityError(
            "That photo's resolution is too high. Take a screenshot of it "
            "and upload that instead."
        )
    if width <= 0 or height <= 0:
        raise SecurityError("The image file appears to be corrupted.")


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
) -> str:
    """
    Run all file-level security checks before any processing.
    Raises SecurityError with a user-friendly message if anything fails.

    Returns the detected file kind: "pdf" or "image". Callers should
    branch extraction logic on this rather than trusting the extension
    or MIME header, since the magic-bytes check is the only one of the
    three that can't be spoofed.
    """
    logger.info(f"[security] Checking upload: {filename}, "
                f"size={len(file_bytes)}, mime={mimetype}, ip={ip_address}")

    # Rate limits first — fastest check, no file reading needed
    if ip_address:
        _rate_limiter.check_ip(ip_address)
    if session_id:
        _rate_limiter.check_session(session_id)

    # Cheap, spoofable checks first — fail fast before the real check
    _check_extension(filename)
    _check_mime(mimetype)

    # Ground-truth check: what does the file actually contain?
    kind = _detect_kind(file_bytes)

    _check_file_size(file_bytes, kind)
    if kind == "image":
        _check_image_dimensions(file_bytes)

    logger.info(f"[security] Upload passed all checks: {filename} (kind={kind})")
    return kind


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
