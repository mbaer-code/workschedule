# This file now acts as the application factory and entry point with robust error handling.
import os
import sys

from flask import Flask, request, redirect, url_for, flash, session, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.exc import SQLAlchemyError
from google.cloud import storage
from werkzeug.utils import secure_filename

import workschedule.services.ics_delivery

from dotenv import load_dotenv
import logging

# --- Firebase Admin SDK Imports ---
import firebase_admin
from firebase_admin import credentials

# Load environment variables at the very beginning
load_dotenv()
logging.debug(".env file loaded.")

# --- Initialize Extensions outside create_app for CLI visibility ---
db = SQLAlchemy()
migrate = Migrate()

# --- Initialize Firebase Admin SDK once ---
# Check if a Firebase app is already initialized to prevent issues with Flask's debug reloader.
try:
    if not firebase_admin._apps:
        # Determine credentials based on environment
        if os.environ.get("K_SERVICE"):
            # This is for running on Cloud Run, which uses ApplicationDefault credentials.
            cred = credentials.ApplicationDefault()
            logging.debug("Using ApplicationDefault credentials for Cloud Run.")
        else:
            # This is for local development. You must provide the path to your
            # Firebase service account key JSON file in an environment variable.
            key_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY")
            logging.error(f"key_path: {key_path}.")
            if not key_path or not os.path.exists(key_path):
                logging.error("FIREBASE_SERVICE_ACCOUNT_KEY environment variable not set or file does not exist.")
                logging.error("HINT: On local machines, you must provide a service account key file for Firebase Admin SDK.")
                sys.exit(1)
            cred = credentials.Certificate(key_path)
            logging.debug(f"Using service account key from {key_path}")
        firebase_admin.initialize_app(cred)
        logging.debug("Firebase Admin SDK initialized successfully.")
    else:
        logging.debug("Firebase Admin SDK was already initialized.")
except Exception as e:
    logging.error(f"Failed to initialize Firebase Admin SDK: {e}")
    sys.exit(1)


logging.debug("Extensions initialized.")

# --- Google Cloud Storage client setup ---
try:
    storage_client = storage.Client()
    #GCS_BUCKET_NAME = os.environ.get("FIREBASE_STORAGE_BUCKET", "your-gcs-bucket-name")
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "gs://work-schedule-cloud/")
    gcs_bucket = storage_client.bucket(GCS_BUCKET_NAME)
except Exception as e:
    logging.error(f"Failed to initialize Google Cloud Storage client: {e}")
    storage_client = None
    gcs_bucket = None

def create_app():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(
        __name__,
        static_folder=os.path.join(base_dir, 'static'),
        template_folder=os.path.join(base_dir, 'templates')
    )

    # Use SQLALCHEMY_DATABASE_URI from Config class for correct Cloud Run/local DB connection
    from workschedule.config import Config
    app.config["SQLALCHEMY_DATABASE_URI"] = Config.SQLALCHEMY_DATABASE_URI

    # Initialize SQLAlchemy with the app
    db.init_app(app)
    # Initialize Flask-Migrate with the app and db
    migrate.init_app(app, db)

    # Register schedule blueprint after app is created
    from workschedule.routes.schedule import schedule_bp
    app.register_blueprint(schedule_bp)

    # --- NEW ROUTES FOR PDF UPLOAD ---
    # These routes are part of the main app, not a blueprint.

    # Print all registered routes for debugging
    print("\n[DEBUG] Registered routes:")
    for rule in app.url_map.iter_rules():
        print(rule)

    @app.route("/schedule/upload")
    def schedule_upload():
        return render_template("upload_schedule_new.html")

    @app.route("/upload", methods=["POST"])
    def upload_file():
        # Check if the required fields are in the form data
        if "email" not in request.form or "timezone" not in request.form or "pdfFile" not in request.files:
            flash("Missing form data. Please fill out all fields.", "error")
            return redirect(url_for("upload_schedule"))

        email = request.form["email"]
        timezone = request.form["timezone"]
        file = request.files["pdfFile"]

        # Validate that a file was actually selected
        if file.filename == "":
            flash("No file selected.", "error")
            return redirect(url_for("upload_schedule"))

        # Validate the file type and name
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            
            # Upload the file directly to Google Cloud Storage
            if gcs_bucket:
                try:
                    # Use a unique path for each user's file
                    blob_path = f"schedules/{email}/{filename}"
                    blob = gcs_bucket.blob(blob_path)
                    
                    # Upload the file directly from the request stream
                    blob.upload_from_file(file)

                    print(f"File uploaded to GCS: {blob_path}")
                    flash("Schedule uploaded successfully!", "success")

                except Exception as e:
                    flash(f"An error occurred during file upload: {e}", "error")
                    print(f"GCS upload failed: {e}")
            else:
                flash("GCS is not configured correctly. Upload failed.", "error")
        else:
            flash("Invalid file type. Please upload a PDF file.", "error")

        return redirect(url_for("dashboard"))
    # --- END OF NEW ROUTES ---


    # Root route and /index route render index.html directly
    @app.route('/')
    @app.route('/index')
    def index():
        return render_template('index.html')
    
    @app.route("/dashboard")
    def dashboard():
        # Placeholder for your dashboard logic
        return "Dashboard page"
    

    return app

# Gunicorn (used by Cloud Run) will look for a top-level 'app' object.
app = create_app()

logging.debug("App factory finished. App instance created.")
print("app.py loaded")

