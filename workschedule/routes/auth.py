# src/routes/auth.py
# This file defines the blueprint for authentication routes.

import os
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from functools import wraps
# --- Firebase Admin SDK Imports ---
import firebase_admin
from firebase_admin import credentials, auth
from firebase_admin import exceptions

# A blueprint is an object that records operations to be applied to a Flask app.
# It is used here to group related authentication routes.
auth_bp = Blueprint('auth_bp', __name__, url_prefix='/auth')
print("DEBUG: auth.py blueprint created and loaded.")
# -----------------------------

# --- Initialize Firebase Admin SDK if not already initialized ---
# This check is crucial for handling the app factory pattern.
# We ensure the SDK is initialized before any functions in this blueprint
# attempt to use it, preventing the 'default Firebase app does not exist' error.
# The credentials file should be in the root directory and excluded from git.
if not firebase_admin._apps:
    print("DEBUG: Initializing Firebase Admin SDK from auth.py.")
    
    # Load the Firebase service account key from an environment variable.
    # We check for a common naming convention, and then a more specific one.
    service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH') or os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY_PATH')

    if not service_account_path:
        print("ERROR: FIREBASE_SERVICE_ACCOUNT_PATH not set.")
        # This will need to be configured for local and cloud run.
        # Fallback to a hardcoded path for local testing
        try:
            cred = credentials.Certificate('instance/service-account.json')
            firebase_admin.initialize_app(cred)
            print("DEBUG: Firebase Admin SDK initialized successfully with fallback.")
        except Exception as e:
            print(f"ERROR: Failed to initialize Firebase Admin SDK: {e}")
    else:
        try:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            print("DEBUG: Firebase Admin SDK initialized successfully.")
        except Exception as e:
            print(f"ERROR: Failed to initialize Firebase Admin SDK with service account path: {e}")
            # Consider raising an exception or handling this more gracefully.

# --- Login Required Decorator ---
# This decorator protects routes, ensuring a user is logged in
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # We now check for the user in the session
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('auth_bp.login_page'))
        return f(*args, **kwargs)
    return decorated_function

# Route for the signup page
@auth_bp.route('/signup')
def signup_page():
    return render_template('auth/signup.html')

# Route for the login page
@auth_bp.route('/login')
def login_page():
    return render_template('auth/login.html')

# --- NEW: Endpoint to receive and verify Firebase ID Token ---
@auth_bp.route('/authenticate-session', methods=['POST'])
def authenticate_session():
    print("\n--- Received /authenticate-session request ---") # DEBUG
    auth_header = request.headers.get('Authorization')
    print(f"Authorization header: {auth_header}") # DEBUG

    if not auth_header or not auth_header.startswith('Bearer '):
        print("ERROR: No Firebase ID token provided or malformed header.") # DEBUG
        return jsonify({'error': 'No Firebase ID token provided.'}), 401

    id_token = auth_header.split('Bearer ')[1]
    print(f"Extracted ID Token: {id_token}") # DEBUG: Print full token for inspection

    try:
        # Verify the ID token using the Firebase Admin SDK with a clock skew tolerance
        # The maximum allowed value for clock_skew_seconds is 60.
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=60)
        uid = decoded_token['uid']
        #session['email'] = decoded_token.get('email')
        #session['name'] = decoded_token.get('name')

        print(f"Firebase ID Token successfully verified for UID: {uid}") # DEBUG
        # Set the user ID in the Flask session
        session['user_id'] = uid


        session.permanent = True # Make the session persistent
        print(f"Flask session 'user_id' set to: {session.get('user_id')}") # DEBUG

        return jsonify({'message': 'Session successfully established.'}), 200

    except ValueError as e:
        # This typically indicates a malformed token.
        print(f"ValueError during token processing (malformed token): {e}") # DEBUG
        return jsonify({"error": "Invalid token format"}), 400
    except exceptions.FirebaseError as e:
        # This handles expired, invalid, or "used too early" tokens
        print(f"Firebase AuthError: {e}") # DEBUG
        return jsonify({"error": "Firebase authentication failed", "details": str(e)}), 401
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Unexpected error in /authenticate-session: {e}") # DEBUG
        import traceback # DEBUG: To print the full traceback
        traceback.print_exc() # DEBUG: Print full traceback to console
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500


# --- Server-Side Logout Route ---
@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth_bp.login_page'))

# --- NEW: Basic dashboard page for logged-in users ---
@auth_bp.route('/dashboard')
@login_required
def dashboard_page():

    user_id = session.get('user_id', '(not found)')
    email = session.get('email', '(email not found)')
    name  = session.get('name', '(name not found)')


    print("Session at /dashboard:", dict(session))
    print("user_id at /dashboard:", user_id )
    return render_template('dashboard.html', user_id=user_id, email=email, name=name )


# --- NEW: Route to test Secret Manager variables ---
@auth_bp.route('/test-secrets')
@login_required
def test_secrets():
    # Retrieve secrets from environment variables
    email_api_key = os.getenv('EMAIL_SERVICE_API_KEY')
    stripe_secret_key = os.getenv('STRIPE_SECRET_KEY')
    
    return jsonify({
        "status": "success",
        "message": "Secrets retrieved from environment variables.",
        "secrets": {
            "EMAIL_SERVICE_API_KEY": email_api_key,
            "STRIPE_SECRET_KEY": stripe_secret_key
        }
    })

# --- NEW: Route to render the upload schedule page ---
@auth_bp.route('/upload_schedule')
def upload_schedule_page():
    return render_template('auth/upload_schedule.html')

