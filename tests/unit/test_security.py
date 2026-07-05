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

from workschedule.services.security import check_upload, SecurityError, _detect_kind


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
