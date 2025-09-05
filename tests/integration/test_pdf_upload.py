import io
import pytest
from workschedule.app import app

def test_pdf_upload_success(monkeypatch):
    client = app.test_client()
    data = {
        'email': 'test@example.com',
        'timezone': 'PST',
        'pdfFile': (io.BytesIO(b'%PDF-1.4 test pdf content'), 'test.pdf')
    }

    # Monkeypatch GCS upload to avoid real network calls
    class DummyBlob:
        def upload_from_file(self, file, content_type=None):
            pass
    class DummyBucket:
        def blob(self, filename):
            return DummyBlob()
    class DummyStorageClient:
        def bucket(self, name):
            return DummyBucket()
    monkeypatch.setattr('google.cloud.storage.Client', DummyStorageClient)

    response = client.post('/schedule/upload_pdf', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"File" in response.data or b"review" in response.data

def test_pdf_upload_missing_file():
    client = app.test_client()
    data = {
        'email': 'test@example.com',
        'timezone': 'PST'
    }
    response = client.post('/schedule/upload_pdf', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b"Missing fields" in response.data or b"upload" in response.data
