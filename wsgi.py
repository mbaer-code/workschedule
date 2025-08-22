# wsgi.py
# This is the main entry point for the Flask application.


import sys
import os
import logging

# Add the project's 'src' directory to the system path to enable module imports
# from the 'routes' package. This fixes the 'ModuleNotFoundError'.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from flask import Flask
from src.routes.auth import auth_bp

# Create the Flask application instance.
# We explicitly set the template_folder and static_folder to point to their
# respective directories relative to the main application file.
# This fixes the "TemplateNotFound" error by telling Flask where to look for your
# HTML and asset files.
app = Flask(__name__, template_folder='src/templates', static_folder='src/static')

# Set a secret key for session management.
# It's best practice to load this from an environment variable for security.
# This fixes the "RuntimeError: The session is unavailable" issue.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_unique_and_secret_fallback_key")

# Register the authentication blueprint with the application.
app.register_blueprint(auth_bp)

# The following is a simple "hello world" route for the root URL
@app.route('/')
def hello_world():
    return 'Hello, World!'

# This block is required to run the development server.
# The `if __name__ == '__main__':` check ensures that the server only runs
# when the script is executed directly (not when it's imported as a module).
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.debug("Starting Flask development server on 0.0.0.0:8080")
    app.run(host='0.0.0.0', port=8080, debug=True)

