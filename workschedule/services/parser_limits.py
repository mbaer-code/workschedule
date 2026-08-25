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

    # Maximum estimated events allowed in the text slice sent to the
    # extraction pass. This is a DENSITY check, not a length check — a
    # long but sparse document (a syllabus, a long itinerary) is fine;
    # a short but event-dense one (a multi-terminal port schedule with
    # a ship + times on nearly every line) is not.
    #
    # The estimate itself is a rough proxy (see _estimate_event_density),
    # not an exact count — some document formats (e.g. an exam schedule
    # with 4 time columns per row: class-start range + exam-time range)
    # trip the time-token heuristic without actually producing that many
    # output events. Rather than chase a perfect estimator, this limit is
    # set high enough to only catch genuinely extreme cases, while the
    # extraction call's max_tokens=8192 (~217 event capacity) covers the
    # real worst case a 6000-char input slice could produce (~150 rows
    # even at a dense ~40 chars/row). This check exists mainly as a
    # courtesy — a fast, free, pre-API "yeah don't bother" for documents
    # that are obviously the wrong shape for a personal calendar sync.
    max_estimated_events: int = field(
        default_factory=lambda: int(os.getenv("MAX_ESTIMATED_EVENTS", "180"))
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
    # Image checks (phone photos of schedules)
    # ------------------------------------------------------------------

    # Maximum upload size for images. Modern phone camera JPEGs typically
    # run 2-8MB; 10MB is generous headroom without inviting abuse.
    max_image_size_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024
    )

    # Minimum image size — anything smaller is almost certainly not a
    # legible photo of a schedule.
    min_image_size_bytes: int = field(
        default_factory=lambda: int(os.getenv("MIN_IMAGE_SIZE_BYTES", "512"))
    )

    # Maximum decoded pixel count (width * height). Protects against
    # decompression-bomb files: a tiny file on disk that decodes to a
    # huge in-memory bitmap. 40 megapixels comfortably covers modern
    # phone cameras (typically 12-48MP) while capping worst-case memory.
    max_image_pixels: int = field(
        default_factory=lambda: int(os.getenv("MAX_IMAGE_PIXELS", str(40_000_000)))
    )

    # After validation, images are normalized/resized before being sent
    # to the AI. This caps the longest edge in pixels — schedule text
    # stays legible well below this, and it keeps vision token cost and
    # latency bounded regardless of the original photo's resolution.
    max_image_dimension: int = field(
        default_factory=lambda: int(os.getenv("MAX_IMAGE_DIMENSION", "2000"))
    )

    # Multiple photos of the same document (e.g. multi-page schedule, or
    # a schedule app screen that needed several scrolled screenshots) can
    # be uploaded together and merged in one vision call. Capped at 5 —
    # MB's own real multi-photo test needed 5 to cover a 3-week schedule
    # without gaps, so 4 was cutting it too close for a real document.
    max_photos_per_upload: int = field(
        default_factory=lambda: int(os.getenv("MAX_PHOTOS_PER_UPLOAD", "5"))
    )

    # Combined size across all photos in one multi-photo upload. Each
    # individual photo still has to pass max_image_size_bytes on its own;
    # this additionally bounds the total, since 5 photos each just under
    # the per-image cap could otherwise add up to a very large request.
    max_combined_image_size_bytes: int = field(
        default_factory=lambda: int(
            os.getenv("MAX_COMBINED_IMAGE_SIZE_MB", "20")) * 1024 * 1024
    )

    # Blur/legibility guard: rejects a photo whose sharpness score (see
    # _image_sharpness_score in security.py -- a Laplacian-edge-variance
    # proxy, pure PIL, no numpy/opencv) falls below this. 0 = disabled
    # (log-only mode). Defaulting to disabled deliberately -- there's no
    # real calibration data yet for what score separates "fine" from
    # "the AI is going to hallucinate this." Every image upload still
    # logs its score either way, so real numbers (a known-blurry photo
    # vs. a normal one) can be collected first; once there's a real
    # threshold, enable it via this env var with no code change needed.
    min_image_sharpness: float = field(
        default_factory=lambda: float(os.getenv("MIN_IMAGE_SHARPNESS", "0"))
    )

    # ------------------------------------------------------------------
    # HARDCODED — do not expose as env vars (security-critical)
    # ------------------------------------------------------------------

    # PDF and phone-photo image formats accepted. Period.
    # .heic/.heif included because iPhone's native camera format is HEIC —
    # without it, "Take Photo" uploads fail unpredictably depending on
    # iOS/browser settings that decide whether to auto-convert to JPEG.
    allowed_extensions: tuple = ('.pdf', '.png', '.jpg', '.jpeg', '.heic', '.heif')

    # MIME types we accept from the browser.
    allowed_mime_types: tuple = (
        'application/pdf',
        'application/x-pdf',
        'application/octet-stream',  # some browsers send this for PDFs
        'image/png',
        'image/jpeg',
        'image/heic',
        'image/heif',
    )

    # First bytes of every valid PDF file.
    # Cannot be faked by renaming a file or setting a MIME header.
    pdf_magic_bytes: bytes = b'%PDF'

    # First bytes of every valid PNG file.
    png_magic_bytes: bytes = b'\x89PNG\r\n\x1a\n'

    # First 3 bytes of every valid JPEG file (SOI marker + APP marker start).
    jpeg_magic_bytes: bytes = b'\xff\xd8\xff'

    # HEIC/HEIF files don't have a fixed leading signature like PDF/PNG/JPEG.
    # Instead, bytes 4-8 are always the ISO base media file format box type
    # "ftyp", and bytes 8-12 carry a brand identifying the specific format.
    # These are the brands iPhones actually produce.
    heic_ftyp_brands: tuple = (
        b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis',
        b'mif1', b'msf1',
    )


# Singleton — import this everywhere rather than instantiating per request.
limits = ParserLimits()
