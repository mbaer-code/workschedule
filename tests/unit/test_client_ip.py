"""
Unit tests for _client_ip(), which extracts the real visitor IP from
Cloud Run's X-Forwarded-For header rather than trusting request.remote_addr
directly.

Regression coverage for a production bug where every visitor was rate
limited as a single shared bucket: Cloud Run's load balancer connects
from an internal address, so request.remote_addr alone reported the same
internal IP (169.254.169.x) for every single visitor regardless of who
they actually were.
"""

from workschedule.app import app


def test_uses_first_ip_in_x_forwarded_for():
    with app.test_request_context(
        '/', headers={'X-Forwarded-For': '203.0.113.5, 169.254.169.126'}
    ):
        from workschedule.routes.schedule import _client_ip
        assert _client_ip() == '203.0.113.5'


def test_strips_whitespace_around_ip():
    with app.test_request_context(
        '/', headers={'X-Forwarded-For': '  203.0.113.5  ,169.254.169.126'}
    ):
        from workschedule.routes.schedule import _client_ip
        assert _client_ip() == '203.0.113.5'


def test_falls_back_to_remote_addr_when_header_absent():
    with app.test_request_context('/', environ_overrides={'REMOTE_ADDR': '198.51.100.9'}):
        from workschedule.routes.schedule import _client_ip
        assert _client_ip() == '198.51.100.9'
