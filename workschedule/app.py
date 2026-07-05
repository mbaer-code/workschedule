# Application factory — all DB/SQLAlchemy code removed; GCS is the data layer.
import os
import sys

from flask import Flask, request, redirect, url_for, flash, render_template
from google.cloud import storage
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
import logging

# --- Firebase Admin SDK Imports ---
import firebase_admin
from firebase_admin import credentials

# Load environment variables at the very beginning
load_dotenv()
logging.debug(".env file loaded.")

# --- Initialize Firebase Admin SDK once ---
# Check if a Firebase app is already initialized to prevent issues with Flask's debug reloader.
try:
    if not firebase_admin._apps:
        if os.environ.get("K_SERVICE"):
            # Cloud Run: use Application Default Credentials
            cred = credentials.ApplicationDefault()
            logging.debug("Using ApplicationDefault credentials for Cloud Run.")
        else:
            # Local dev: use service account key file
            key_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY")
            logging.error(f"key_path: {key_path}.")
            if not key_path or not os.path.exists(key_path):
                logging.error("FIREBASE_SERVICE_ACCOUNT_KEY not set or file does not exist.")
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
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "work-schedule-cloud")
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

    # Flask session secret key
    app.secret_key = (
        os.environ.get('MAGIC_LINK_SECRET')
        or os.environ.get('SECRET_KEY')
        or os.environ.get('FLASK_SECRET_KEY')
        or 'change-me-in-dev'
    )

    # Register schedule blueprint
    from workschedule.routes.schedule import schedule_bp
    app.register_blueprint(schedule_bp)

    # NOTE: auth_bp (login/signup/Firebase session auth) has been archived —
    # see workschedule/routes/_archived/auth.py.bak. It depended entirely on
    # Firebase Admin SDK verification, which is no longer in use. Every route
    # in it either called Firebase directly or was gated by a login_required
    # decorator that checked a session key only Firebase auth ever set — so
    # none of it functioned even when the blueprint was (recently, briefly)
    # registered.
    #
    # One route in that blueprint had no Firebase dependency at all —
    # /auth/upload_schedule, a plain form page — so it's preserved here
    # standalone rather than lost along with the rest.
    @app.route('/auth/upload_schedule')
    def auth_upload_schedule_page():
        return render_template('auth/upload_schedule.html')

    # Print registered routes for debugging
    print("\n[DEBUG] Registered routes:")
    for rule in app.url_map.iter_rules():
        print(rule)

    @app.route('/')
    @app.route('/index')
    def index():
        return render_template('index.html')

    @app.route("/dashboard")
    def dashboard():
        return "Dashboard page"

    return app


# Gunicorn (used by Cloud Run) will look for a top-level 'app' object.
app = create_app()

logging.debug("App factory finished. App instance created.")
print("app.py loaded")
