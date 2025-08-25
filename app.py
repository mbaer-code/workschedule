# app.py
# This file now acts as the application factory and entry point with robust error handling.
import os
import sys
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.exc import SQLAlchemyError

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
            logging.error("key_path: {key_path}.")
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

def create_app():
    """
    Creates and configures the Flask application.
    """
    app = Flask(__name__, static_folder='src/static', template_folder='src/templates')
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_unique_and_secret_fallback_key")

    logging.debug(f"App object created. {app.secret_key}")
    
    # --- Database Configuration ---
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    
    db_uri = None

    if os.environ.get("K_SERVICE"):
        # This branch is for running on Cloud Run
        instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")
        if not all([db_user, db_pass, db_name, instance_connection_name]):
            logging.error("Missing one or more database environment variables for Cloud Run.")
            sys.exit(1)
        db_uri = f"postgresql://{db_user}:{db_pass}@/{db_name}?host=/cloudsql/{instance_connection_name}"
    else:
        # This branch is for local development
        if not all([db_user, db_pass, db_name]):
            logging.error("Missing DB_USER, DB_PASS, or DB_NAME environment variables.")
            sys.exit(1)
        db_uri = f"postgresql://{db_user}:{db_pass}@127.0.0.1:5432/{db_name}"

    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    logging.debug(f"Attempting to connect to database using URI: {db_uri}")

    # Initialize extensions with the app using a try-except block for better error reporting
    try:
        with app.app_context():
            db.init_app(app)
            migrate.init_app(app, db)
        logging.debug("Database connection successful!")
    except SQLAlchemyError as e:
        logging.error(f"Failed to connect to the database: {e}")
        sys.exit(1)
    
    # --- Register Blueprints ---
    logging.debug("Attempting to import blueprints...")
    from src.routes.schedule import schedule_bp
    from src.routes.auth import auth_bp
    logging.debug("Blueprints imported successfully.")
    
    app.register_blueprint(schedule_bp)
    app.register_blueprint(auth_bp)

    # A simple root route to redirect to the authentication page
    @app.route('/')
    def index():
        return redirect(url_for('auth_bp.login_page'))

    return app

# Gunicorn (used by Cloud Run) will look for a top-level 'app' object.
app = create_app()

logging.debug("App factory finished. App instance created.")


