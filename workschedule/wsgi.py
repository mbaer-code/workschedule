# wsgi.py
# This is the main entry point for the Flask application.

import sys
import os
import logging

# Ensure all debug logs are printed to the terminal
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)

# from the 'routes' package. This fixes the 'ModuleNotFoundError'.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask
from workschedule.app import create_app

# Create the Flask application instance.
app = create_app()

# Set a secret key for session management.
# It's best practice to load this from an environment variable for security.
# This fixes the "RuntimeError: The session is unavailable" issue.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_unique_and_secret_fallback_key")

# Blueprints are registered in create_app(), do not register here.

# Root route is defined in app.py, do not define here.

# This block is required to run the development server.
# The `if __name__ == '__main__':` check ensures that the server only runs
# when the script is executed directly (not when it's imported as a module).
if __name__ == '__main__':
    # Run the Flask development server on all available interfaces and port 8080.
    # This will output the "* Running on..." message to your console, confirming
    # the server is up and running.
    app.run(host='0.0.0.0', port=8080, debug=True)

