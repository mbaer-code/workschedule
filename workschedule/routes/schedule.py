import os
import datetime
import json
import hmac
import hashlib
import time
import re
import uuid

import fitz  # PyMuPDF
import stripe
from flask import (Blueprint, render_template, request, redirect,
                   url_for, jsonify, abort, Response, session)
from werkzeug.utils import secure_filename

from workschedule.services.stripe_service import create_checkout_session
from workschedule.services.pdf_parser import parse_pdf_with_claude

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
    # URL-safe: base64 would be cleaner but hex is fine for short tokens
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

    # Check expiry first
    if time.time() > expires_at:
        raise ValueError("Token has expired.")

    # Verify signature
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
    print(f"[DEBUG] GCS upload: gs://{_bucket_name()}/{blob_path}")


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
        print(f"[DEBUG] GCS delete: gs://{_bucket_name()}/{blob_path}")
    except Exception as e:
        print(f"[DEBUG] GCS delete failed for {blob_path}: {e}")


# ---------------------------------------------------------------------------
# PDF parsing helpers  (unchanged logic, just tidied)
# ---------------------------------------------------------------------------
def extract_text_from_pdf(pdf_contents: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_contents, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""


def parse_schedule_text(text: str) -> list:
    print("=== EXTRACTED TEXT ===")
    print(text[:500] + "..." if len(text) > 500 else text)
    print("=== END EXTRACTED TEXT ===")

    results = []
    if "not assigned" in text.lower() or "not scheduled" in text.lower():
        return results

    full_shift_pattern = re.compile(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})'
        r'\s+(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)'
        r'\s*\[[\d:]+\]\s*(\d{4})\s*-\s*Store\s+(\d{3})',
        re.IGNORECASE
    )
    full_shifts = full_shift_pattern.findall(text)

    if full_shifts:
        print(f"Found {len(full_shifts)} shifts with full store/dept info: {full_shifts}")
        for month, date, start_time, end_time, dept_code, store_code in full_shifts:
            results.append({
                'username': '', 'store_number': f"#{dept_code}", 'weekday': '',
                'month': month, 'date': date,
                'shift_start': start_time, 'meal_start': '', 'meal_end': '',
                'shift_end': end_time, 'department': store_code
            })
    else:
        shift_pattern = re.compile(
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})'
            r'\s+(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)',
            re.IGNORECASE
        )
        shifts = shift_pattern.findall(text)
        store_match = re.search(r'(\d{4})\s*-\s*Store', text)
        dept_match = re.search(r'Store\s+(\d{3})', text)
        default_store = f"#{store_match.group(1)}" if store_match else ''
        default_dept = dept_match.group(1) if dept_match else ''
        print(f"Found {len(shifts)} shifts (fallback), store={default_store}, dept={default_dept}")
        for month, date, start_time, end_time in shifts:
            results.append({
                'username': '', 'store_number': default_store, 'weekday': '',
                'month': month, 'date': date,
                'shift_start': start_time, 'meal_start': '', 'meal_end': '',
                'shift_end': end_time, 'department': default_dept
            })

    print(f"Parsed {len(results)} total shifts")
    return results


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
    if not pdf_file.filename.lower().endswith('.pdf'):
        return render_template("upload_schedule_new.html",
                               pdf_error="Only PDF files are accepted.")

    try:
        pdf_contents = pdf_file.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return redirect(url_for('schedule_bp.upload_schedule'))

    try:
        final_output, doc_title = parse_pdf_with_claude(pdf_contents)
        if not final_output:
            return render_template("review_schedule.html", parsed_schedule=[],
                                   raw_json="No events found in this document. Please check that it contains dates.")

        # Persist to GCS (timezone included, no email)
        job_id = str(uuid.uuid4())
        payload = {
            "timezone": timezone,
            "shifts": final_output,
            "doc_title": doc_title,
        }
        _upload_to_gcs(json.dumps(payload), f"parsed/{job_id}.json")

        session['job_id'] = job_id

        return render_template('review_schedule.html',
                               parsed_schedule=final_output,
                               job_id=job_id)

    except Exception as e:
        print(f"Parsing error: {e}")
        job_id = locals().get('job_id') or session.get('job_id')
        return render_template("review_schedule.html",
                               parsed_schedule=[], raw_json=str(e), job_id=job_id)


@schedule_bp.route('/approve_schedule', methods=['POST'])
def approve_schedule():
    print(f"[DEBUG] approve_schedule: form={request.form}")
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
        customer_email=None,   # no email required anymore
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'job_id': job_id}
    )

    if not stripe_session or not hasattr(stripe_session, 'url'):
        return render_template("review_schedule.html", parsed_schedule=[],
                               raw_json="Stripe session could not be created. Please try again.")

    print(f"[approve_schedule] Redirecting to Stripe: {stripe_session.url}")
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
        raw_title = parsed_data.get('doc_title', '')
        if not parsed_schedule:
            return render_template('link_expired.html'), 410
    except Exception as e:
        print(f"[payment_success] GCS error: {e}")
        return render_template('link_expired.html'), 410

    safe_title = re.sub(r'[^\w\s-]', '', raw_title).strip().replace(' ', '_')[:40] if raw_title else 'schedule'

    # Generate ICS
    from workschedule.services.ics_generator import create_ics_from_entries
    ics_content = create_ics_from_entries(parsed_schedule,
                                          calendar_name=raw_title or "myschedule.cloud",
                                          timezone_str=timezone_str)

    # Store ICS in GCS under ics/ prefix — embed safe title in blob name for download
    ics_blob_path = f"ics/{job_id}_{safe_title}.ics"
    client = _gcs_client()
    bucket = client.bucket(_bucket_name())
    ics_blob = bucket.blob(ics_blob_path)
    ics_blob.upload_from_string(ics_content.encode('utf-8'),
                                content_type='text/calendar')

    # Delete the parsed JSON — no longer needed
    _delete_from_gcs(blob_path)

    # Build magic link token (points to our /download route)
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
        print(f"[download_ics] Token invalid: {e}")
        return render_template('link_expired.html'), 410

    try:
        client = _gcs_client()
        bucket = client.bucket(_bucket_name())
        blobs = list(bucket.list_blobs(prefix=f"ics/{job_id}"))
        if not blobs:
            raise FileNotFoundError("ICS blob not found")
        blob = blobs[0]
        ics_blob_path = blob.name
        ics_content = blob.download_as_bytes()
    except Exception as e:
        print(f"[download_ics] GCS error: {e}")
        return render_template('link_expired.html'), 410

    # Delete from GCS after serving
    _delete_from_gcs(ics_blob_path)

    # Derive friendly filename from blob name: ics/{job_id}_{safe_title}.ics
    blob_basename = ics_blob_path.split('/')[-1]          # e.g. abc123_Thompson_Coburn.ics
    safe_title = blob_basename[len(job_id)+1:]             # strip job_id_ prefix
    now = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    filename = f"{safe_title.replace('.ics', '')}_{now}.ics"
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
        print(f"Stripe webhook error: {e}")
        return abort(400)

    if event['type'] == 'checkout.session.completed':
        stripe_session = event['data']['object']
        job_id = stripe_session.get('metadata', {}).get('job_id')
        print(f"[stripe_webhook] Payment completed for job_id={job_id}")
        # ICS generation happens in payment_success route via redirect;
        # webhook is available here for future server-side fulfillment if needed.

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
