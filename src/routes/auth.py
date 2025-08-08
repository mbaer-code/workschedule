# src/routes/auth.py
# This file defines the blueprint for authentication routes.

import os
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from functools import wraps
# --- Firebase Admin SDK Imports ---
import firebase_admin
from firebase_admin import credentials, auth

# Create a Blueprint for authentication with a URL prefix
# This Blueprint does NOT call create_app() or create a Flask app instance.
auth_bp = Blueprint('auth_bp', __name__, url_prefix='/auth')
print("DEBUG: auth.py blueprint created and loaded.")
# -----------------------------

# --- Login Required Decorator ---
# This decorator will protect routes, ensuring a user is logged in
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
    print(f"Extracted ID Token (first 20 chars): {id_token[:20]}...") # DEBUG

    try:
        # Verify the ID token using the Firebase Admin SDK
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']

        print(f"Firebase ID Token successfully verified for UID: {uid}") # DEBUG
        # Set the user ID in the Flask session
        session['user_id'] = uid
        session.permanent = True # Make the session persistent
        print(f"Flask session 'user_id' set to: {session.get('user_id')}") # DEBUG

        return jsonify({'message': 'Session successfully established.'}), 200

    except ValueError as e:
        print(f"ValueError during token processing: {e}") # DEBUG
        return jsonify({"error": "Invalid token format"}), 400
    except auth.AuthError as e:
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
    return render_template('dashboard.html')

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


