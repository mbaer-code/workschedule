#!/bin/bash

# --- Configuration Variables ---
# IMPORTANT: Replace these with your actual values.
# For DB_PASS, we recommend using Google Cloud Secret Manager.
# Create the secret once using:
# echo -n "YOUR_DB_PASSWORD" | gcloud secrets create DB_PASSWORD_SECRET_NAME --data-file=- --replication-policy="automatic"
# Then, replace 'your-db-password-secret-name' below with your secret's actual name.

CLOUD_RUN_SERVICE_NAME="workschedule-api" # Your chosen Cloud Run service name
GCP_PROJECT_ID="work-schedule-cloud"     # Your Google Cloud Project ID
GCP_REGION="us-central1"                 # Your desired Cloud Run and Cloud SQL region

# Cloud SQL Instance Details
CLOUD_SQL_INSTANCE_CONNECTION_NAME="work-schedule-cloud:us-central1:workschedule-db"
DB_USER="postgres"                       # Your Cloud SQL database username
DB_NAME="workschedule_db"                # Your Cloud SQL database name
DB_PASSWORD_SECRET_NAME="workschedule-db-password" # Name of your secret in Secret Manager

# --- Function to check if a database exists and create it if not ---
# This is a robust way to ensure the database exists before deployment
check_and_create_db() {
    echo "--- Checking and Creating Database '${DB_NAME}' if it does not exist ---"
    local db_exists=false

    # Attempt to connect to the 'postgres' database (default)
    # and query pg_database to see if our target DB_NAME exists.
    # We redirect stderr to /dev/null to suppress "database does not exist" errors
    # if our target DB_NAME isn't there yet.
    if gcloud sql connect "${CLOUD_SQL_INSTANCE_CONNECTION_NAME##*:}" \
        --user="${DB_USER}" \
        --project="${GCP_PROJECT_ID}" \
        --quiet \
        -- <<EOF 2>/dev/null
SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}';
EOF
    then
        db_exists=true
    fi

    if [ "$db_exists" = true ]; then
        echo "Database '${DB_NAME}' already exists."
    else
        echo "Database '${DB_NAME}' does not exist. Creating it now..."
        if gcloud sql connect "${CLOUD_SQL_INSTANCE_CONNECTION_NAME##*:}" \
            --user="${DB_USER}" \
            --project="${GCP_PROJECT_ID}" \
            --quiet \
            -- <<EOF
CREATE DATABASE ${DB_NAME};
EOF
        then
            echo "Database '${DB_NAME}' created successfully."
        else
            echo "Failed to create database '${DB_NAME}'. Please check permissions and try manually."
            exit 1
        fi
    fi
}

# --- Main Script Execution ---

# 1. First, check/create the database
# NOTE: This part requires the DB_USER to have permissions to CREATE DATABASE.
# The 'postgres' user typically has this. If you use a different user, ensure it has this grant.
check_and_create_db

# 2. Get DB password from Secret Manager securely
echo "--- Retrieving DB Password from Secret Manager ---"
# We need to explicitly access the secret value here if we're passing it via --set-env-vars.
# However, Cloud Run's --set-secrets is generally preferred for direct secret consumption by the service.
# For the database creation step, we will still need it here.
# Ensure your Cloud Shell user or the service account running this script has Secret Manager Secret Accessor role.
DB_PASS=$(gcloud secrets versions access latest \
    --secret="${DB_PASSWORD_SECRET_NAME}" \
    --project="${GCP_PROJECT_ID}" \
    --format="value(payload.data)" || { echo "Failed to retrieve DB password from Secret Manager!"; exit 1; })

# 3. Build the Docker Image
echo "--- Starting Cloud Build for Docker Image ---"
IMAGE_TAG="gcr.io/${GCP_PROJECT_ID}/workschedule-cloud-app"
gcloud builds submit \
  --tag "${IMAGE_TAG}" \
  . || { echo "Cloud Build failed!"; exit 1; }

echo "Cloud Build successful. Image tagged as ${IMAGE_TAG}"

# 4. Deploy to Cloud Run
echo "--- Starting Cloud Run Deployment ---"
gcloud run deploy "${CLOUD_RUN_SERVICE_NAME}" \
  --image "${IMAGE_TAG}" \
  --platform managed \
  --region "${GCP_REGION}" \
  --allow-unauthenticated \
  --add-cloudsql-instances "${CLOUD_SQL_INSTANCE_CONNECTION_NAME}" \
  --set-env-vars "DB_USER=${DB_USER},DB_NAME=${DB_NAME},INSTANCE_CONNECTION_NAME=${CLOUD_SQL_INSTANCE_CONNECTION_NAME}" \
  --set-secrets "DB_PASS=${DB_PASSWORD_SECRET_NAME}:latest" \ # Use --set-secrets for the password
  --project "${GCP_PROJECT_ID}" \
  --no-cpu-throttling \ # Optional: keeps CPU allocated for faster cold starts (can increase cost)
  --min-instances 0 \   # Optional: scale to zero when idle
  --max-instances 1 \   # Optional: limit max instances for cost control or specific needs
  || { echo "Cloud Run deployment failed!"; exit 1; }

echo "Cloud Run deployment successful!"

# 5. Get and Display Service URL
echo "Service URL:"
SERVICE_URL=$(gcloud run services describe "${CLOUD_RUN_SERVICE_NAME}" \
    --platform managed \
    --region "${GCP_REGION}" \
    --format="value(status.url)")
echo "${SERVICE_URL}"

# 6. Final Cleanup (no manual password input to clean up now)
unset DB_PASS # Unset the variable just in case
echo "Deployment script finished."
