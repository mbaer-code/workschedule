import os
import uuid
import datetime
from google.cloud import storage

# --- Configuration ---
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")

# Initialize the storage client once
storage_client = storage.Client()

# --- Helper Functions ---
def _get_bucket_if_exists():
    """Gets the bucket instance and raises an error if the name is not set."""
    if not BUCKET_NAME:
        raise ValueError("The 'GCS_BUCKET_NAME' environment variable is not set.")
    return storage_client.bucket(BUCKET_NAME)

def _upload_ics_to_gcs(ics_content):
    """Uploads the ICS content string to the bucket. Returns the unique file name."""
    bucket = _get_bucket_if_exists()
    file_name = f'calendars/{uuid.uuid4()}.ics'
    blob = bucket.blob(file_name)
    blob.upload_from_string(
        data=ics_content,
        content_type='text/calendar'
    )
    return file_name

def _generate_signed_url(file_name):
    """Generates a secure, time-limited URL for the uploaded file."""
    bucket = _get_bucket_if_exists()
    blob = bucket.blob(file_name)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=5),
        method="GET"
    )
    return url

def deliver_ics_file(ics_content):
    """
    Orchestrates the delivery process: uploads the file and returns a signed URL.
    Args:
        ics_content (str): The string content of the ICS file.
    Returns:
        str: A secure, temporary URL to the ICS file.
    """
    if not ics_content:
        raise ValueError("ICS content cannot be empty.")
    file_name = _upload_ics_to_gcs(ics_content)
    signed_url = _generate_signed_url(file_name)
    return signed_url

def deliver_ics_file_from_path(file_path):
    """
    Takes a path to an existing .ics file, uploads it to a bucket, 
    and returns a secure, time-limited URL.
    Args:
        file_path (str): The local path to the .ics file.
    Returns:
        str: A signed URL for the file in the bucket.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found at path: {file_path}")
    with open(file_path, "r") as f:
        ics_content = f.read()
    return deliver_ics_file(ics_content)

if __name__ == '__main__':
    print("This file is a module and is meant to be imported.")
    print("Run your main application file to test the full workflow.")
