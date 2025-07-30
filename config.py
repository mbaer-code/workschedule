# workschedule-cloud/config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-super-secret-key-replace-in-prod' # IMPORTANT: Replace this with a strong, random key for production!
    # DATABASE_URI will be set via environment variables for Cloud Run/local


class DevelopmentConfig(Config):
    DEBUG = True
    FLASK_ENV = 'development'
    # Add any dev-specific settings here
