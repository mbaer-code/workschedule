import os
import datetime
import json
import hmac
import hashlib
import time
import re
import uuid
import logging

import fitz  # PyMuPDF
import stripe
from flask import (Blueprint, render_template, request, redirect,
                   url_for, jsonify, abort, Response, session)
from werkzeug.utils import secure_filename

from workschedule.services.stripe_service import create_checkout_session
from workschedule.services.security import check_upload, check_text, SecurityError
from workschedule.services.pdf_parser import parse_document_with_summary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
schedule_bp = Blueprint(
    'schedule_bp', __name__,
    url_prefix='/schedule',
    template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates')
)

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
MAGIC_LINK_SECRET = os.getenv("MAGIC_LINK_SECRET", "change-me-in-production")
MAGIC_LINK_TTL_SECONDS = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Magic-link helpers
# ---------------------------------------------------------------------------
def _make_token(job_id: str) -> str:
    """Return a signed token encoding job_id + expiry timestamp."""
    expires_at = int(time.time()) + MAGIC_LINK_TTL_SECONDS
    payload = f"{job_id}:{expires_at}"
    sig = hmac.new(
        MAGIC_LINK_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    import base64
    token = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    return token


def _verify_token(token: str):
    """
    Verify a magic-link token.
    Returns job_id on success, raises ValueError on failure/expiry.
    """
    import base64
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        job_id, expires_at_str, sig = decoded.rsplit(":", 2)
        expires_at = int(expires_at_str)
    except Exception:
        raise ValueError("Invalid token format.")

    if time.time() > expires_at:
        raise ValueError("Token has expired.")

    payload = f"{job_id}:{expires_at_str}"
    expected_sig = hmac.new(
        MAGIC_LINK_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Token signature invalid.")

    return job_id


# ---------------------------------------------------------------------------
# GCS helpers
# ---------------------------------------------------------------------------
def _gcs_client():
    from google.cloud import storage
    return storage.Client()


def _bucket_name():
    return os.environ.get('GCS_BUCKET_NAME', 'work-schedule-cloud')


def _upload_to_gcs(data: str, blob_path: str):
    client = _gcs_client()
    bucket = client.bucket(_bucket_name())
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data, content_type='application/json')
    logger.debug(f"GCS upload: gs://{_bucket_name()}/{blob_path}")


def _download_from_gcs(blob_path: str) -> str:
    client = _gcs_client()
    bucket = client.bucket(_bucket_name())
    blob = bucket.blob(blob_path)
    return blob.download_as_text()


def _delete_from_gcs(blob_path: str):
    try:
        client = _gcs_client()
        bucket = client.bucket(_bucket_name())
        blob = bucket.blob(blob_path)
        blob.delete()
        logger.debug(f"GCS delete: gs://{_bucket_name()}/{blob_path}")
    except Exception as e:
        logger.warning(f"GCS delete failed for {blob_path}: {e}")


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------
def extract_text_from_pdf(pdf_contents: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_contents, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@schedule_bp.route("/upload", methods=["GET"])
def upload_schedule():
    return render_template("upload_schedule_new.html")


@schedule_bp.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'pdfFile' not in request.files:
        return redirect(url_for('schedule_bp.upload_schedule'))

    pdf_file = request.files['pdfFile']
    timezone = request.form.get('timezone', 'America/Los_Angeles')

    if not pdf_file or pdf_file.filename == '':
        return render_template("upload_schedule_new.html",
                               pdf_error="Please select a PDF file.")

    try:
        pdf_contents = pdf_file.read()
    except Exception as e:
        logger.error(f"Error reading uploaded file: {e}")
        return redirect(url_for('schedule_bp.upload_schedule'))

    # --- Security gate (fast, free, runs before any API call) ---
    try:
        check_upload(
            file_bytes=pdf_contents,
            filename=secure_filename(pdf_file.filename),
            mimetype=pdf_file.content_type,
            ip_address=request.remote_addr,
            session_id=session.get('user_id') or request.remote_addr,
        )
    except SecurityError as e:
        logger.warning(f"[upload_pdf] Security check failed: {e}")
        return render_template("upload_schedule_new.html", pdf_error=str(e))

    try:
        # Extract text from PDF
        extracted_text = extract_text_from_pdf(pdf_contents)

        # Text-level security check + truncation if needed
        try:
            safe_text = check_text(extracted_text)
        except SecurityError as e:
            return render_template("review_schedule.html", parsed_schedule=[],
                                   raw_json=str(e))

        # Parse document — single call returns both events and summary (2 API calls)
        parsed_entries, doc_summary = parse_document_with_summary(safe_text)
        logger.info(f"[upload_pdf] Document detected: {doc_summary}")

        if not parsed_entries:
            return render_template("review_schedule.html", parsed_schedule=[],
                                   doc_summary=doc_summary,
                                   raw_json="No calendar events found in this document.")

        # Sort by date
        parsed_entries.sort(key=lambda x: x.get('shift_date', ''))

        # Persist to GCS
        job_id = str(uuid.uuid4())
        payload = {
            "timezone": timezone,
            "shifts": parsed_entries
        }
        _upload_to_gcs(json.dumps(payload), f"parsed/{job_id}.json")
        session['job_id'] = job_id

        return render_template('review_schedule.html',
                               parsed_schedule=parsed_entries,
                               doc_summary=doc_summary,
                               job_id=job_id)

    except Exception as e:
        logger.error(f"[upload_pdf] Unexpected error: {e}", exc_info=True)
        job_id = locals().get('job_id') or session.get('job_id')
        return render_template("review_schedule.html",
                               parsed_schedule=[], raw_json=str(e), job_id=job_id)


@schedule_bp.route('/approve_schedule', methods=['POST'])
def approve_schedule():
    logger.debug(f"approve_schedule: form={request.form}")
    job_id = request.form.get('job_id') or request.args.get('job_id')
    if not job_id:
        return render_template("review_schedule.html", parsed_schedule=[],
                               raw_json="No job_id found. Cannot proceed to payment.")

    # Verify the GCS blob exists before sending to Stripe
    try:
        _download_from_gcs(f"parsed/{job_id}.json")
    except Exception as e:
        return render_template("review_schedule.html", parsed_schedule=[],
                               raw_json=f"Could not load schedule data: {e}")

    # Build Stripe session
    success_url = f"{BASE_URL}/schedule/payment_success?job_id={job_id}"
    cancel_url = f"{BASE_URL}/schedule/payment_cancel"
    price_id = os.getenv("STRIPE_PRICE_ID")

    stripe_session = create_checkout_session(
        price_id,
        customer_email=None,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'job_id': job_id}
    )

    if not stripe_session or not hasattr(stripe_session, 'url'):
        return render_template("review_schedule.html", parsed_schedule=[],
                               raw_json="Stripe session could not be created. Please try again.")

    logger.info(f"[approve_schedule] Redirecting to Stripe: {stripe_session.url}")
    return redirect(stripe_session.url)


@schedule_bp.route('/payment_success', methods=['GET'])
def payment_success():
    job_id = request.args.get('job_id')
    if not job_id:
        return render_template('link_expired.html'), 410

    blob_path = f"parsed/{job_id}.json"

    try:
        schedule_json = _download_from_gcs(blob_path)
        parsed_data = json.loads(schedule_json)
        parsed_schedule = parsed_data.get('shifts', [])
        timezone_str = parsed_data.get('timezone', 'America/Los_Angeles')
        if not parsed_schedule:
            return render_template('link_expired.html'), 410
    except Exception as e:
        logger.error(f"[payment_success] GCS error: {e}")
        return render_template('link_expired.html'), 410

    # Generate ICS
    from workschedule.services.ics_generator import create_ics_from_entries
    ics_content = create_ics_from_entries(parsed_schedule,
                                          calendar_name="myschedule.cloud",
                                          timezone_str=timezone_str)

    # Store ICS in GCS under ics/ prefix
    ics_blob_path = f"ics/{job_id}.ics"
    client = _gcs_client()
    bucket = client.bucket(_bucket_name())
    ics_blob = bucket.blob(ics_blob_path)
    ics_blob.upload_from_string(ics_content.encode('utf-8'),
                                content_type='text/calendar')

    # Delete the parsed JSON — no longer needed
    _delete_from_gcs(blob_path)

    # Build magic link token
    token = _make_token(job_id)
    magic_link = f"{BASE_URL}/schedule/download/{token}"

    return render_template('payment_success.html',
                           ics_link=magic_link,
                           message="Payment successful. Your schedule is ready.",
                           success=True)


@schedule_bp.route('/download/<token>', methods=['GET'])
def download_ics(token):
    """Verify HMAC token, serve ICS, then delete from GCS."""
    try:
        job_id = _verify_token(token)
    except ValueError as e:
        logger.warning(f"[download_ics] Token invalid: {e}")
        return render_template('link_expired.html'), 410

    ics_blob_path = f"ics/{job_id}.ics"
    try:
        client = _gcs_client()
        bucket = client.bucket(_bucket_name())
        blob = bucket.blob(ics_blob_path)
        ics_content = blob.download_as_bytes()
    except Exception as e:
        logger.error(f"[download_ics] GCS error: {e}")
        return render_template('link_expired.html'), 410

    # Delete from GCS after serving
    _delete_from_gcs(ics_blob_path)

    now = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    filename = f"work_schedule_{now}.ics"
    response = Response(ics_content, mimetype="text/calendar")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


@schedule_bp.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.error(f"Stripe webhook error: {e}")
        return abort(400)

    if event['type'] == 'checkout.session.completed':
        stripe_session = event['data']['object']
        job_id = stripe_session.get('metadata', {}).get('job_id')
        logger.info(f"[stripe_webhook] Payment completed for job_id={job_id}")

    return '', 200


@schedule_bp.route('/payment_cancel', methods=['GET'])
def payment_cancel():
    return render_template('payment_cancel.html')


@schedule_bp.route('/create-checkout-session', methods=['POST'])
def create_session():
    price_id = os.getenv("STRIPE_PRICE_ID")
    stripe_session = create_checkout_session(price_id, customer_email=None)
    if stripe_session:
        return jsonify({'id': stripe_session.id})
    return jsonify({'error': 'Failed to create checkout session'}), 500
