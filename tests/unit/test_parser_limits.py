"""
tests/unit/test_parser_limits.py
---------------------------------
Focused coverage for ParserLimits.photo_upload_enabled -- the feature
flag gating photo/vision upload off by default (see its docstring in
parser_limits.py). The default-closed behavior is the safety-critical
part: a regression here would silently re-expose the fabrication bug
this flag exists to gate off, so it's worth its own direct test rather
than relying only on the route/template checks.
"""
import pytest
from workschedule.services.parser_limits import ParserLimits


class TestPhotoUploadEnabledFlag:

    def test_defaults_to_disabled_when_env_var_unset(self, monkeypatch):
        monkeypatch.delenv("PHOTO_UPLOAD_ENABLED", raising=False)
        assert ParserLimits().photo_upload_enabled is False

    def test_disabled_when_env_var_is_false(self, monkeypatch):
        monkeypatch.setenv("PHOTO_UPLOAD_ENABLED", "false")
        assert ParserLimits().photo_upload_enabled is False

    def test_disabled_on_any_unrecognized_value(self, monkeypatch):
        """Fails closed, not open -- an unexpected/typo'd value should
        never accidentally re-enable this."""
        monkeypatch.setenv("PHOTO_UPLOAD_ENABLED", "yes")
        assert ParserLimits().photo_upload_enabled is False

    def test_enabled_when_explicitly_set_true(self, monkeypatch):
        monkeypatch.setenv("PHOTO_UPLOAD_ENABLED", "true")
        assert ParserLimits().photo_upload_enabled is True

    def test_enabled_value_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("PHOTO_UPLOAD_ENABLED", "True")
        assert ParserLimits().photo_upload_enabled is True
