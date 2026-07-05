# Application factory — all DB/SQLAlchemy code removed; GCS is the data layer.
import os
import sys

from flask import Flask, request, redirect, url_for, flash, render_template
from google.cloud import storage
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
import logging

# Load environment variables at the very beginning
load_dotenv()
logging.debug(".env file loaded.")

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
    # see workschedule/routes/_archived/. It depended entirely on Firebase
    # Admin SDK verification. This product doesn't support login or save
    # user data — it's stateless, anonymous, review-before-pay — so there
    # was never a real login/dashboard flow for this to plug into. Nothing
    # in the live app ever linked to any of it.

    # Print registered routes for debugging
    print("\n[DEBUG] Registered routes:")
    for rule in app.url_map.iter_rules():
        print(rule)

    @app.route('/')
    @app.route('/index')
    def index():
        return render_template('index.html')

    return app


# Gunicorn (used by Cloud Run) will look for a top-level 'app' object.
app = create_app()

logging.debug("App factory finished. App instance created.")
print("app.py loaded")
