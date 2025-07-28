# app.py (or a new file like src/database.py if you prefer modularity)
import os
from flask import Flask
import psycopg2 # Make sure psycopg2-binary is in your requirements.txt
from sqlalchemy import create_engine, text # If using SQLAlchemy

def create_app():
    app = Flask(__name__)

    # --- Database Configuration ---
    # Get database connection details from environment variables
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASS")
    db_name = os.environ.get("DB_NAME")
    # THIS IS THE CRITICAL LINE: Ensure it reads from INSTANCE_CONNECTION_NAME
    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")

    # Construct the database URI for Cloud SQL
    # The Cloud SQL Proxy creates a Unix socket at /cloudsql/INSTANCE_CONNECTION_NAME
    db_uri = f"postgresql://{db_user}:{db_pass}@/{db_name}?host=/cloudsql/{instance_connection_name}"

    # Store db_uri in app config for later use
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False # Suppress warning

    # Example: Simple route to test database connection
    @app.route('/')
    def hello_world():
        try:
            # Attempt to connect to the database
            conn = psycopg2.connect(db_uri)
            cursor = conn.cursor()
            cursor.execute("SELECT version();") # Simple query to test connection
            db_version = cursor.fetchone()[0]
            conn.close()
            return f"Hello, World! Your Flask app is running. Database connected successfully! PostgreSQL version: {db_version}"
        except Exception as e:
            # Return the actual error message for debugging
            return f"Hello, World! Your Flask app is running. Database connection error: {e}"

    return app

# If you're running app.py directly (not via wsgi.py and create_app()):
# app = create_app()
# if __name__ == '__main__':
#     app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

