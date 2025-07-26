
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# --- Cloud SQL Configuration ---
# These will be set as environment variables on Cloud Run from Secret Manager later
# For local development, you might set dummy values or use a local PostgreSQL for testing
DB_USER = os.getenv('DB_USER', 'postgres') # Default for simplicity, change later for your specific DB user
DB_PASS = os.getenv('DB_PASS', 'your_local_dev_password') # Use a dummy for local dev
DB_NAME = os.getenv('DB_NAME', 'my_database') # Default for local, change for your specific DB name
# This comes from the Cloud SQL instance connection name (e.g., project-id:region:instance-id)
CLOUD_SQL_CONNECTION_NAME = os.getenv('CLOUD_SQL_CONNECTION_NAME', 'your-local-connection-name') # Dummy for local

# Determine connection string based on environment
if os.getenv('K_SERVICE'): # This env var is set by Cloud Run for its services
    # Unix socket connection for Cloud Run
    DB_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@/{DB_NAME}?host=/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"
else:
    # Local connection for development (adjust if you use a local PostgreSQL server)
    # For quick local testing without a local PG server, you can temporarily comment out DB parts
    # or use SQLite: app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
    # If you want to test local Postgres, ensure it's running and accessible at localhost:5432
    DB_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@localhost:5432/{DB_NAME}"


app.config['SQLALCHEMY_DATABASE_URI'] = DB_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Suppress warning

db = SQLAlchemy(app)

# --- Basic User Table Schema ---
class User(db.Model):
    id = db.Column(db.String(128), primary_key=True) # Firebase UID will go here
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Add more fields later: subscription_status, prompt_frequency, etc.

    def __repr__(self):
        return f'<User {self.email}>'

# --- Flask Routes ---
@app.route('/')
def hello_world():
    # Test database connection (optional, for debugging)
    db_status = "Database not initialized or connected locally yet."
    try:
        # This line will try to query the User table. It will fail if the table doesn't exist.
        user_count = db.session.query(User).count()
        db_status = f"Database connected. User count: {user_count}"
    except Exception as e:
        # Catch specific errors for missing table or general connection issues
        if "relation \"user\" does not exist" in str(e) or "no such table" in str(e) or "Table 'user' doesn't exist" in str(e):
            db_status = "Database connected, 'user' table not yet created. Run db.create_all() locally."
        else:
            db_status = f"Database connection error: {e}"

    return f'Hello, World! Your Flask app is running. {db_status}'

# This block only runs when you execute app.py directly (e.g., for local dev)
# Gunicorn will be used when deployed to Cloud Run.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)

