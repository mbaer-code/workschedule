#!/bin/bash

# This script sets up the recommended filesystem structure for the
# 'workschedule-cloud' Flask project.
#
# IMPORTANT: Run this script from the root of your 'workschedule-cloud' directory.
# If you have existing files (e.g., app.py, requirements.txt), this script
# will create empty placeholders. You will need to manually move your
# existing code into these new files after running the script.

echo "Creating core project directories..."

# Root level directories
mkdir -p .devcontainer
mkdir -p .github/workflows
mkdir -p .vscode
mkdir -p instance
mkdir -p migrations/versions
mkdir -p tests/unit
mkdir -p tests/integration

# Source code (src) directories
mkdir -p src/routes
mkdir -p src/services
mkdir -p src/templates/auth
mkdir -p src/templates/dashboard
mkdir -p src/templates/payments
mkdir -p src/templates/emails
mkdir -p src/static/css
mkdir -p src/static/js
mkdir -p src/static/img

echo "Creating placeholder files..."

# Root level files
touch app.py
touch config.py
touch Dockerfile
touch requirements.txt
touch wsgi.py
touch .dockerignore
touch .env
touch README.md

# Add initial content to .gitignore
echo "# Python virtual environment" >> .gitignore
echo "venv/" >> .gitignore
echo "" >> .gitignore
echo "# Local environment variables (DO NOT COMMIT)" >> .gitignore
echo ".env" >> .gitignore
echo "" >> .gitignore
echo "# Python build artifacts and cache" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "*.pyo" >> .gitignore
echo "*.pyd" >> .gitignore
echo "" >> .gitignore
echo "# Instance-specific configuration" >> .gitignore
echo "instance/*" >> .gitignore
echo "!instance/.gitkeep" >> .gitignore # Allow empty instance folder to be committed if needed

# Add initial content to .dockerignore
echo "venv/" >> .dockerignore
echo ".git/" >> .dockerignore
echo ".gitignore" >> .dockerignore
echo ".env" >> .dockerignore
echo ".vscode/" >> .dockerignore
echo ".devcontainer/" >> .dockerignore
echo "tests/" >> .dockerignore
echo "*.pyc" >> .dockerignore
echo "__pycache__/" >> .dockerignore
echo "instance/" >> .dockerignore # Don't copy local instance config to Docker image

# Instance files
touch instance/config.py
touch instance/.gitkeep # Optional: To keep the empty directory in Git

# Migrations files (placeholders for Alembic)
touch migrations/env.py
touch migrations/script.py.mako

# Test files (placeholders)
touch tests/__init__.py
touch tests/unit/test_parsing.py
touch tests/unit/test_ics_generation.py
touch tests/integration/test_auth_flow.py
touch tests/integration/test_pdf_upload.py

# Source code (src) __init__.py files for packages
touch src/__init__.py
touch src/routes/__init__.py
touch src/services/__init__.py

# Placeholder for models
touch src/models.py

# Placeholder route files
touch src/routes/auth.py
touch src/routes/dashboard.py
touch src/routes/schedule.py
touch src/routes/feeds.py

# Placeholder service files
touch src/services/pdf_parser.py
touch src/services/ics_generator.py
touch src/services/stripe_service.py
touch src/services/email_service.py
touch src/services/db_service.py

# Placeholder template files
touch src/templates/base.html
touch src/templates/auth/login.html
touch src/templates/auth/signup.html
touch src/templates/dashboard/index.html
touch src/templates/dashboard/upload.html
touch src/templates/payments/pricing.html
touch src/templates/emails/welcome_email.html
touch src/templates/emails/prompt_upload_email.html

# Placeholder static files
touch src/static/css/style.css
touch src/static/js/main.js
touch src/static/img/logo.png

echo "Filesystem structure created successfully!"
echo "Remember to move your existing code into the new placeholder files."
echo "Also, ensure your Python virtual environment is set up (e.g., 'python -m venv venv') and add your local .env variables."
