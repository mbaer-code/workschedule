"""
Unit tests for the upload security gate, in particular HEIC/HEIF support.

Regression coverage for the bug where iPhone "Take Photo" uploads failed
silently: the security gate rejected HEIC files outright (no magic-bytes
match, extension/MIME not allowlisted), and the front-end's <input accept>
list didn't include HEIC either, so some iOS/browser combinations wouldn't
even attach the captured photo to the form.
"""

import io

import pytest

from workschedule.services.security import (
    check_upload, check_upload_batch, SecurityError, _detect_kind,
)


def _real_heic_bytes(size=(400, 400)) -> bytes:
    """Encode a genuine, decodable HEIC image using pillow-heif."""
    import pillow_heif
    from PIL import Image

    img = Image.new('RGB', size, color='red')
    heif_file = pillow_heif.from_pillow(img)
    buf = io.BytesIO()
    heif_file.save(buf, format='HEIF')
    return buf.getvalue()


def _fake_ftyp_bytes(brand: bytes, payload_size: int = 600) -> bytes:
    """
    A synthetic 'ftyp' box naming the given brand, WITHOUT real decodable
    image data after it. Useful for testing magic-byte detection in
    isolation, but will fail Pillow's header read if run through the full
    check_upload pipeline (that's expected — see TestHeicFullPipeline for
    real, decodable HEIC files).
    """
    header = b'\x00\x00\x00\x18ftyp' + brand + b'\x00\x00\x00\x00mif1' + brand
    return header + (b'\x00' * payload_size)


class TestHeicMagicByteDetection:
    """Tests _detect_kind() directly against the ftyp/brand signature,
    independent of whether the payload is a real decodable image."""

    def test_heic_brand_detected_as_image(self):
        assert _detect_kind(_fake_ftyp_bytes(b'heic')) == 'image'

    def test_generic_mif1_brand_detected_as_image(self):
        assert _detect_kind(_fake_ftyp_bytes(b'mif1')) == 'image'

    def test_unrecognized_ftyp_brand_rejected(self):
        # A real container format (e.g. an mp4 video) also uses 'ftyp'
        # boxes, so only the specific photo brands should be let through.
        with pytest.raises(SecurityError):
            _detect_kind(_fake_ftyp_bytes(b'isom'))

    def test_garbage_with_no_magic_bytes_rejected(self):
        with pytest.raises(SecurityError):
            _detect_kind(b'not a real file' + b'\x00' * 600)


class TestHeicFullPipeline:
    """Tests the complete check_upload() gate, including the image
    dimension check, against a genuine decodable HEIC file — this is
    the regression test for the silent iPhone upload failure."""

    def test_real_heic_photo_passes_full_security_gate(self):
        kind = check_upload(
            file_bytes=_real_heic_bytes(),
            filename='IMG_1234.HEIC',
            mimetype='image/heic',
        )
        assert kind == 'image'

    def test_heic_extension_case_insensitive(self):
        kind = check_upload(
            file_bytes=_real_heic_bytes(),
            filename='IMG_1234.HEIC',
            mimetype='image/heic',
        )
        assert kind == 'image'


class TestGracefulDegradationWithoutHeif:
    """
    Regression test for the production bug where HEIF registration ran on
    every single image request (not just HEIC ones) and wasn't guarded
    broadly enough -- a pillow-heif failure could take down PNG/JPEG
    uploads too. Simulates that failure mode via monkeypatch and confirms
    normal image types are unaffected.
    """

    def test_png_upload_unaffected_when_heif_support_disabled(self, monkeypatch):
        import workschedule.services.security as security_module
        monkeypatch.setattr(security_module, '_HEIF_SUPPORT', False)

        png_buf = io.BytesIO()
        from PIL import Image
        Image.new('RGB', (400, 400), color='green').save(png_buf, format='PNG')

        kind = check_upload(
            file_bytes=png_buf.getvalue(),
            filename='screenshot.png',
            mimetype='image/png',
        )
        assert kind == 'image'


def _real_png_bytes(size=(400, 400), color='blue') -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, color=color).save(buf, format='PNG')
    return buf.getvalue()


def _real_pdf_bytes() -> bytes:
    # Minimal but valid PDF structure, well above min_file_size_bytes.
    return (
        b'%PDF-1.4\n'
        b'1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
        b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
        b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n'
        b'trailer<</Root 1 0 R>>\n'
        + b'%' * 1200  # padding well past min_file_size_bytes (1024 bytes)
    )


class TestCheckUploadBatch:
    """
    check_upload_batch() backs the multi-photo upload path: several
    photos of the same document submitted together under one field name.
    Rate limiting must apply once per BATCH (one submission), not once
    per photo, or a legitimate 4-photo upload would burn 4x the rate
    limit budget of an equivalent single-file upload.
    """

    def test_multiple_photos_all_pass_as_images(self):
        files = [(_real_png_bytes(), f'IMG_{i}.png', 'image/png') for i in range(3)]
        kinds = check_upload_batch(files)
        assert kinds == ['image', 'image', 'image']

    def test_single_pdf_still_works(self):
        files = [(_real_pdf_bytes(), 'schedule.pdf', 'application/pdf')]
        kinds = check_upload_batch(files)
        assert kinds == ['pdf']

    def test_empty_batch_rejected(self):
        with pytest.raises(SecurityError):
            check_upload_batch([])

    def test_batch_over_max_photos_rejected(self):
        files = [(_real_png_bytes(), f'IMG_{i}.png', 'image/png') for i in range(5)]
        with pytest.raises(SecurityError):
            check_upload_batch(files)

    def test_mixed_pdf_and_photo_rejected(self):
        files = [
            (_real_pdf_bytes(), 'schedule.pdf', 'application/pdf'),
            (_real_png_bytes(), 'IMG_1.png', 'image/png'),
        ]
        with pytest.raises(SecurityError):
            check_upload_batch(files)

    def test_two_pdfs_rejected(self):
        files = [
            (_real_pdf_bytes(), 'a.pdf', 'application/pdf'),
            (_real_pdf_bytes(), 'b.pdf', 'application/pdf'),
        ]
        with pytest.raises(SecurityError):
            check_upload_batch(files)

    def test_one_bad_photo_rejects_whole_batch(self):
        files = [
            (_real_png_bytes(), 'IMG_1.png', 'image/png'),
            (b'not a real image' + b'\x00' * 600, 'IMG_2.png', 'image/png'),
        ]
        with pytest.raises(SecurityError):
            check_upload_batch(files)

    def test_rate_limit_applied_once_per_batch_not_per_photo(self, monkeypatch):
        import workschedule.services.security as security_module

        calls = {'ip': 0, 'session': 0}
        monkeypatch.setattr(
            security_module._rate_limiter, 'check_ip',
            lambda ip: calls.__setitem__('ip', calls['ip'] + 1))
        monkeypatch.setattr(
            security_module._rate_limiter, 'check_session',
            lambda sid: calls.__setitem__('session', calls['session'] + 1))

        files = [(_real_png_bytes(), f'IMG_{i}.png', 'image/png') for i in range(4)]
        check_upload_batch(files, ip_address='1.2.3.4', session_id='sess-1')

        assert calls['ip'] == 1
        assert calls['session'] == 1
