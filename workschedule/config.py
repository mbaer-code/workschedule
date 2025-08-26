# workschedule-cloud/config.py
import os

class Config:
    # Flask application settings
    # IMPORTANT: Replace 'your-super-secret-key-replace-in-prod' with a truly random,
    # long string for production deployments. Use environment variables (e.g., Secret Manager)
    # in Cloud Run for SECRET_KEY.
    FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'a_fallback_secret_key_for_pure_dev_not_prod'

    # Environment settings
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    DEBUG = (FLASK_ENV == 'development')

    # Cloud SQL Connection Name (for Cloud Run production)
    # This value will be crucial for Cloud Run to connect via the Cloud SQL Connector.
    # In Cloud Run, you will set this as an environment variable.
    # For local development with the Cloud SQL Proxy, you can also set it in your .env.
    CLOUD_SQL_CONNECTION_NAME = os.environ.get(
        'CLOUD_SQL_CONNECTION_NAME',
        'work-schedule-cloud:us-central1:workschedule-db' # Default for local testing ease
    )

    # Database Credentials (fetched from environment variables)
    # These MUST be set in your .env file for local development,
    # and as secrets (e.g., from Secret Manager) in Cloud Run.
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_NAME = os.environ.get('DB_NAME')

    # SQLAlchemy Database URI (dynamically generated based on environment)
    # Cloud Run detection: `K_SERVICE` environment variable is set by Cloud Run.
    if CLOUD_SQL_CONNECTION_NAME and os.environ.get('K_SERVICE'):
        # Running on Cloud Run: Use Unix socket connection via Cloud SQL Connector
        # Format: postgresql+psycopg2://<user>:<password>@/<dbname>?host=/cloudsql/<INSTANCE_CONNECTION_NAME>
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@"
            f"/{DB_NAME}?host=/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"
        )
    else:
        # Running locally (or anywhere not detected as Cloud Run): Use standard TCP connection
        # DB_HOST and DB_PORT will come from .env for local development (e.g., localhost:5432 with proxy)
        DB_HOST = os.environ.get('DB_HOST', 'localhost')
        DB_PORT = os.environ.get('DB_PORT', '5432')
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )

    # Recommended to suppress SQLAlchemy warning
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Firebase Admin SDK configuration
    # For local development, you might use a service account key file.
    # In Cloud Run, Application Default Credentials will be used (service account attached to Cloud Run).
    FIREBASE_SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH')


# You can keep your DevelopmentConfig if you have specific dev-only overrides,
# but for database connection, the main Config class should handle both.
# If you have specific debug logging or other settings, you can add them here.
class DevelopmentConfig(Config):
    DEBUG = True
    FLASK_ENV = 'development'
    # Example: If you want to use a different database name for local dev vs. prod
    # DB_NAME = os.environ.get('DB_NAME', 'workschedule_dev_local') 
    # (But it's usually simpler to just manage DB_NAME via .env and Cloud Run env vars)

