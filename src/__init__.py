# workschedule-cloud/src/__init__.py

import os
from flask import Flask, render_template

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    # Load default configuration
    app.config.from_object('config.DevelopmentConfig')

    # ensure the instance folder exists (for app.instance_path)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Route for the signup page
    @app.route('/signup')
    def signup_page():
        return render_template('auth/signup.html')

    # Route for the login page (and also make root go to login for now)
    @app.route('/')
    @app.route('/login')
    def login_page():
        return render_template('auth/login.html')

    # --- NEW: Dashboard Route ---
    @app.route('/dashboard')
    def dashboard():
        # In the future, you'd load user-specific data here
        # For now, just a placeholder
        return "<h1>Welcome to the Dashboard! You are logged in.</h1><p><a href='/logout'>Logout</a></p>"

    # Register blueprints (we'll add auth blueprint later)
    # from .routes import auth_bp
    # app.register_blueprint(auth_bp)

    return app
