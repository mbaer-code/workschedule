# workschedule-cloud/src/__init__.py
import os
from flask import Flask, render_template, session, redirect, url_for, request, flash, jsonify
from functools import wraps # Needed for decorators

# --- New Imports for Firebase Admin SDK ---
import firebase_admin
from firebase_admin import credentials, auth

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    
    # Load default configuration
    app.config.from_object('config.DevelopmentConfig')

    # --- Flask Secret Key for Sessions ---
    # This MUST be kept secret!
    # Your provided key is now securely set here.
    app.config['SECRET_KEY'] = 'e453e674c3a56d0cfd4a2b43c8e94f6bd23cce45029d00c9'
    
    # ensure the instance folder exists (for app.instance_path)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- Initialize Firebase Admin SDK ---
    # Path to your service account key file.
    # This file should be in your 'instance/' folder and NOT committed to Git!
    SERVICE_ACCOUNT_KEY_FILENAME = 'work-schedule-cloud-36477-firebase-adminsdk-fbsvc-08527b1d8d.json' # Your actual filename is now here!
    SERVICE_ACCOUNT_KEY_PATH = os.path.join(app.instance_path, SERVICE_ACCOUNT_KEY_FILENAME)
    
    # Ensure the service account key file exists
    if not os.path.exists(SERVICE_ACCOUNT_KEY_PATH):
        # This will stop the app from starting if the key is missing
        raise FileNotFoundError(
            f"Firebase service account key not found at {SERVICE_ACCOUNT_KEY_PATH}. "
            "Please download it from Firebase console (Project settings -> Service accounts) "
            "and place it in your 'instance/' folder."
        )

    # Initialize the Firebase Admin SDK
    if not firebase_admin._apps: # Check if Firebase is already initialized to prevent re-initialization
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        firebase_admin.initialize_app(cred)
        app.logger.info("Firebase Admin SDK initialized successfully.")
    else:
        app.logger.info("Firebase Admin SDK already initialized.")


    # --- Login Required Decorator ---
    # This decorator will protect routes, ensuring a user is logged in
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # For now, we only check if 'user_id' is in session.
            # Later, we will verify Firebase ID tokens here using the Firebase Admin SDK.
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'info')
                return redirect(url_for('login_page'))
            return f(*args, **kwargs)
        return decorated_function

    # Route for the signup page
    @app.route('/signup')
    def signup_page():
        return render_template('auth/signup.html')

    # Route for the login page (and also make root go to login for now)
    @app.route('/')
    @app.route('/login')
    def login_page():
        return render_template('auth/login.html')

    # --- NEW: Endpoint to receive and verify Firebase ID Token ---
    @app.route('/authenticate-session', methods=['POST'])
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
    @app.route('/logout', methods=['GET', 'POST']) # Allow both GET (for direct access) and POST (from JS)
    def logout():
        session.pop('user_id', None) # Remove user_id from Flask session
        flash('You have been logged out.', 'success')
        return redirect(url_for('login_page'))


    # --- Protected Dashboard Route ---
    @app.route('/dashboard')
    @login_required # Apply the decorator to protect this route
    def dashboard():
        # In the future, you'd load user-specific data here
        user_id = session.get('user_id') # Get user_id from session
        return render_template('dashboard.html', user_id=user_id) # Pass user_id to template


    # Error handling for 404 Not Found (optional: create 404.html)
    @app.errorhandler(404)
    def page_not_found(e):
        # IMPORTANT: If you don't have a 404.html template, this will cause a TemplateNotFound error.
        # For now, you can return a simple string if you don't want to create the file:
        return "<h1>404 Not Found</h1><p>The page you requested was not found.</p>", 404
        # If you have a 404.html in your 'templates' folder, uncomment the line below:
        # return render_template('404.html'), 404
        
    return app
