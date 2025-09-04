from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    jsonify,
    current_app # Use this to access the app context
)
from werkzeug.utils import secure_filename
from workschedule.services.stripe_service import create_checkout_session
from workschedule.services.mailgun_service import send_simple_message
import uuid
import os
import psycopg2
from google.cloud import storage

# Create a blueprint for schedule-related routes
schedule_bp = Blueprint("schedule_bp", __name__, url_prefix="/schedule")

# --- SIMULATING THE DATABASE ---
job_database = {}

def is_first_time_user_db_check(email):
    """
    Simulates a check on the PostgreSQL database.
    """
    conn = None
    print(f"DEBUG: Checking database for first-time user: {email}") # New debug message
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        cur = conn.cursor()

        # Check if the users table exists, and create it if it doesn't
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL
            );
        """)
        conn.commit()

        # Now, check if the user's email exists
        cur.execute("SELECT COUNT(*) FROM users WHERE email = %s;", (email,))
        count = cur.fetchone()[0]
        cur.close()

        # If the email is not in the table, it's a first-time user.
        # We also insert the new user's email to ensure they don't get a free trial again.
        if count == 0:
            insert_cur = conn.cursor()
            insert_cur.execute("INSERT INTO users (email) VALUES (%s);", (email,))
            conn.commit()
            insert_cur.close()
            return True
        
        return False

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Database connection or query failed: {error}")
        return False
    finally:
        if conn is not None:
            conn.close()

# --- ROUTES ---

@schedule_bp.route("/upload_schedule_new")
def upload_schedule_new():
    return render_template("upload_schedule_new.html")

@schedule_bp.route("/upload_pdf", methods=["POST"])
def upload_pdf():
    # --- DEBUGGING PRINTS ---
    # Print the form data and files received by the server
    print("Received Form Data:", request.form)
    print("Received Files:", request.files)
    # --- END DEBUGGING PRINTS ---

    # Check if the required fields are in the form data
    if (
        "email" not in request.form
        or "timezone" not in request.form
        or not ("pdfFile" in request.files or "pdffile" in request.files)
    ):
        flash("Missing form data. Please fill out all fields.", "error")
        return redirect(url_for("schedule_bp.upload_schedule_new"))

    # Determine the correct key for the file
    file_key = "pdfFile" if "pdfFile" in request.files else "pdffile"

    email = request.form["email"]
    timezone = request.form["timezone"]
    file = request.files[file_key]

    # Validate that a file was actually selected
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("schedule_bp.upload_schedule_new"))

    # Validate the file type and name
    if file and file.filename.endswith(".pdf"):
        filename = secure_filename(file.filename)
        job_id = str(uuid.uuid4())
        unique_filename = f"{job_id}_{filename}"

        # --- IMPLEMENT THE FREE TRIAL CHECK ---
        is_free_trial = is_first_time_user_db_check(email)
        
        # --- GCS UPLOAD LOGIC ---
        try:
            # Get GCS bucket from environment variable
            gcs_bucket_name = os.getenv("GCS_BUCKET_NAME")
            if not gcs_bucket_name:
                print("DEBUG: GCS_BUCKET_NAME environment variable is not set. Redirecting.")
                flash("GCS bucket name is not configured.", "error")
                return redirect(url_for("schedule_bp.upload_schedule_new"))

            storage_client = storage.Client()
            bucket = storage_client.bucket(gcs_bucket_name)

            # Use a unique path for each user's file
            blob_path = f"schedules/{email}/{unique_filename}"
            blob = bucket.blob(blob_path)
            
            # Upload the file directly from the request stream
            file.stream.seek(0)
            blob.upload_from_file(file.stream)

            print(f"File uploaded to GCS: {blob_path}. Job ID: {job_id}")

        except Exception as e:
            flash(f"An error occurred during file upload: {e}", "error")
            print(f"GCS upload failed: {e}")
            # This return statement is crucial to avoid the Type Error
            return redirect(url_for("schedule_bp.upload_schedule_new"))

        # Simulate job creation in our temporary database
        job_database[job_id] = {'email': email, 'filename': unique_filename, 'is_free_trial': is_free_trial}
        print(f"File processed. Job ID: {job_id}")
        
        # --- SEND EMAIL AND REDIRECT BASED ON FREE TRIAL ---
        email_sent = False
        if is_free_trial:
            subject = "Your Free Schedule Conversion is Ready!"
            body = f"Hi there!\n\nYour schedule has been successfully converted. Click the link below to download your ICS file:\n\n{url_for('schedule_bp.download_file', job_id=job_id, _external=True)}\n\nEnjoy your free trial!\n\nBest regards,\nSchedule to ICS"
            email_sent = send_simple_message(email, subject, body)
            if email_sent:
                return redirect(url_for("schedule_bp.download_file", job_id=job_id))
        else:
            subject = "Complete Your Schedule Conversion"
            body = f"Hi there!\n\nYour schedule has been successfully converted and is ready for download. Please click the link below to complete your payment and get your ICS file:\n\n{url_for('schedule_bp.pay', job_id=job_id, _external=True)}\n\nThanks for your continued support!\n\nBest regards,\nSchedule to ICS"
            email_sent = send_simple_message(email, subject, body)
            if email_sent:
                return redirect(url_for("schedule_bp.pay", job_id=job_id))
        
        if not email_sent:
            flash("An error occurred while sending the email. Please try again or contact support.", "error")
            return redirect(url_for("schedule_bp.upload_schedule_new"))
    else:
        flash("Invalid file type. Please upload a PDF file.", "error")
        return redirect(url_for("schedule_bp.upload_schedule_new"))
        
@schedule_bp.route("/download/<job_id>")
def download_file(job_id):
    """
    Renders the free trial download page.
    """
    job_info = job_database.get(job_id)
    if not job_info:
        flash("Invalid download link.", "error")
        return redirect(url_for("schedule_bp.upload_schedule_new"))
    return render_template("download_page.html", job_id=job_id)
    
@schedule_bp.route("/pay/<job_id>")
def pay(job_id):
    """
    Renders the dedicated payment page after looking up the email by job ID.
    """
    job_info = job_database.get(job_id)
    if not job_info:
        flash("Invalid payment link. Please try uploading your schedule again.", "error")
        return redirect(url_for("schedule_bp.upload_schedule_new"))
    customer_email = job_info['email']
    return render_template("payments/payment_page.html", customer_email=customer_email)
    
@schedule_bp.route("/create-checkout-session", methods=["POST"])
def create_checkout_session_route():
    try:
        data = request.get_json()
        customer_email = data.get('email')
        price_id = "price_1PqS6oB7Yt0dFh2L0Q7eL8yW"
        session = create_checkout_session(price_id, customer_email)
        if session:
            return jsonify({"id": session.id})
        return jsonify({"error": "Failed to create session."}), 500
    except Exception as e:
        return jsonify(error=str(e)), 400

