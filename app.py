# app.py
# This file now acts as the application factory and entry point with robust error handling.
import os
import sys
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Load environment variables at the very beginning
load_dotenv()
print("DEBUG: .env file loaded.")

# --- Initialize Extensions outside create_app for CLI visibility ---
db = SQLAlchemy()
migrate = Migrate()

print("DEBUG: Extensions initialized.")

def create_app():
    """
    Creates and configures the Flask application.
    """
    app = Flask(__name__, static_folder='src/static', template_folder='src/templates')
    app.secret_key = os.urandom(24)

    print("DEBUG: App object created.")
    
    # --- Database Configuration ---
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    
    db_uri = None

    if os.environ.get("K_SERVICE"):
        # This branch is for running on Cloud Run
        instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")
        if not all([db_user, db_pass, db_name, instance_connection_name]):
            print("ERROR: Missing one or more database environment variables for Cloud Run.", file=sys.stderr)
            sys.exit(1)
        db_uri = f"postgresql://{db_user}:{db_pass}@/{db_name}?host=/cloudsql/{instance_connection_name}"
    else:
        # This branch is for local development
        if not all([db_user, db_pass, db_name]):
            print("ERROR: Missing DB_USER, DB_PASS, or DB_NAME environment variables.", file=sys.stderr)
            sys.exit(1)
        db_uri = f"postgresql://{db_user}:{db_pass}@127.0.0.1:5432/{db_name}"

    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    print(f"DEBUG: Attempting to connect to database using URI: {db_uri}")

    # Initialize extensions with the app using a try-except block for better error reporting
    try:
        with app.app_context():
            db.init_app(app)
            migrate.init_app(app, db)
        print("DEBUG: Database connection successful!")
    except SQLAlchemyError as e:
        print(f"ERROR: Failed to connect to the database: {e}", file=sys.stderr)
        sys.exit(1)
    
    # --- Register Blueprints ---
    # The fix for the circular import is to move these imports inside the factory function.
    print("DEBUG: Attempting to import blueprints...")
    from src.routes.schedule import schedule_bp
    from src.routes.auth import auth_bp
    print("DEBUG: Blueprints imported successfully.")
    
    # --- IMPORTANT NOTE ---
    # The traceback indicates the circular import is caused by a call to `create_app()`
    # from within `src/routes/auth.py`. To fix this, you must remove that call from
    # the auth.py file. Blueprints should not create the application instance.
    # ----------------------
    
    # We now register both the schedule and auth blueprints.
    app.register_blueprint(schedule_bp)
    app.register_blueprint(auth_bp)

    # A simple root route to redirect to the authentication page
    @app.route('/')
    def index():
        return redirect(url_for('auth_bp.login_page'))

    return app

# Gunicorn (used by Cloud Run) will look for a top-level 'app' object.
app = create_app()

print("DEBUG: App factory finished. App instance created.")
