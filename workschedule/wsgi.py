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

# Session secret key is set inside create_app() (checks MAGIC_LINK_SECRET,
# then SECRET_KEY, then FLASK_SECRET_KEY, then a dev-only fallback — in
# that priority order). Do not set it again here: this used to overwrite
# it with a narrower check (FLASK_SECRET_KEY only) and a hardcoded
# fallback string, which silently downgraded session signing to a
# checked-in-source secret any time MAGIC_LINK_SECRET or SECRET_KEY was
# set but FLASK_SECRET_KEY wasn't.

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

