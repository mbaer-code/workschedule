"""
ics_delivery.py

Legacy helper kept for compatibility. The primary delivery flow now goes
through schedule.py (upload → GCS → HMAC token → /download/<token>).

If you need to generate a raw GCS signed URL directly, use deliver_ics_file().
"""
import os
import uuid
import datetime
from google.cloud import storage

BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
storage_client = storage.Client()


def _get_bucket():
    if not BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME environment variable is not set.")
    return storage_client.bucket(BUCKET_NAME)


def _upload_ics_to_gcs(ics_content: str) -> str:
    """Upload ICS content to GCS, return blob path."""
    bucket = _get_bucket()
    file_name = f'ics/{uuid.uuid4()}.ics'
    blob = bucket.blob(file_name)
    blob.upload_from_string(ics_content, content_type='text/calendar')
    return file_name


def _generate_signed_url(file_name: str) -> str:
    """Generate a 1-hour signed URL for the given blob."""
    bucket = _get_bucket()
    blob = bucket.blob(file_name)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(hours=1),
        method="GET"
    )
    return url


def deliver_ics_file(ics_content: str) -> str:
    """
    Upload ICS content to GCS and return a signed URL valid for 1 hour.
    Note: the new primary flow uses HMAC tokens via schedule.py instead.
    """
    if not ics_content:
        raise ValueError("ICS content cannot be empty.")
    file_name = _upload_ics_to_gcs(ics_content)
    return _generate_signed_url(file_name)


def deliver_ics_file_from_path(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, "r") as f:
        ics_content = f.read()
    return deliver_ics_file(ics_content)


if __name__ == '__main__':
    print("This file is a module — import it rather than running directly.")
