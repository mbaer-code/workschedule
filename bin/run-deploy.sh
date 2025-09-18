#!/bin/bash

# --- Configuration Variables ---
# DB_PASSWORD, uses Google Cloud Secret Manager.

CLOUD_RUN_SERVICE_NAME="workschedule-api" # Your chosen Cloud Run service name
GCP_PROJECT_ID="work-schedule-cloud"     # Your Google Cloud Project ID
GCP_REGION="us-central1"                 # Your desired Cloud Run and Cloud SQL region

# --- Verify Authenticated User ---
echo "--- Verifying Authenticated gcloud User ---"
AUTH_USER=$(gcloud config get-value account)
echo "Authenticated as: ${AUTH_USER}"
echo "----------------------------------------"

# Cloud SQL Instance Details
CLOUD_SQL_INSTANCE_CONNECTION_NAME="work-schedule-cloud:us-central1:workschedule-db"
CLOUD_SQL_CONNECTION_NAME="work-schedule-cloud:us-central1:workschedule-db"
DB_USER="postgres"                       # Your Cloud SQL database username
DB_NAME="workschedule_db"                # Your Cloud SQL database name

# Secret Manager variable names (no version suffix)
DB_PASSWORD_SECRET_NAME="workschedule-db-password:latest"
STRIPE_SECRET_KEY="STRIPE_SECRET_KEY:latest"
MAILGUN_API_SECRET_NAME="workschedule-mailgun-api-key:latest"

# Other config
STRIPE_PRICE_ID="price_1S5WunIDZ9jjdH6b8iKTMc7r" # test
#STRIPE_PRICE_ID="price_1S3hfCRNuiIIf8E1Xi4p8gLw" # live
BASE_URL="https://www.myschedule.cloud"
GCS_BUCKET_NAME="work-schedule-cloud"
MAILGUN_REPLY_TO="reply@myschedule.cloud"
MAILGUN_DOMAIN="mg.myschedule.cloud"


# Document AI and pdf processing
GOOGLE_CLOUD_PROJECT_ID="work-schedule-cloud"
PROJECT_ID="work-schedule-cloud"
DOCUMENT_AI_LOCATION="us"
LOCATION="us"
DOCUMENT_AI_PROCESSOR_ID="fe0baaa28beedbe9"
PROCESSOR_ID="fe0baaa28beedbe9"

# --- Function to check if a database exists and create it if not ---

check_and_create_db() {
    echo "--- 1.  Checking and Creating Database '${DB_NAME}' if it does not exist ---"

    # Attempt to describe the database to check if it exists
    if gcloud sql databases describe "${DB_NAME}" \
        --instance="${CLOUD_SQL_INSTANCE_CONNECTION_NAME##*:}" \
        --project="${GCP_PROJECT_ID}" &>/dev/null; then
        echo "Database '${DB_NAME}' already exists."
    else
        echo "Database '${DB_NAME}' does not exist. Creating it now..."
        if gcloud sql databases create "${DB_NAME}" \
            --instance="${CLOUD_SQL_INSTANCE_CONNECTION_NAME##*:}" \
            --project="${GCP_PROJECT_ID}"; then
            echo "Database '${DB_NAME}' created successfully."
        else
            echo "Failed to create database '${DB_NAME}'. Please check permissions."
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
echo "--- 2. Retrieving DB Password from Secret Manager ---"
# We need to explicitly access the secret value here if we're passing it via --set-env-vars.
# However, Cloud Run's --set-secrets is generally preferred for direct secret consumption by the service.
# For the database creation step, we will still need it here.
# Ensure your Cloud Shell user or the service account running this script has Secret Manager Secret Accessor role.
DB_PASSWORD=$(gcloud secrets versions access \
    --secret="${DB_PASSWORD_SECRET_NAME}" \
    --project="${GCP_PROJECT_ID}" \
    --format="value(payload.data)" || { echo "Failed to retrieve DB password from Secret Manager!"; exit 1; })

# 3. Build the Docker Image
echo "--- 3.  Starting Cloud Build for Docker Image ---"
IMAGE_TAG="gcr.io/${GCP_PROJECT_ID}/workschedule-cloud-app"
echo "--- Image TAG = ${IMAGE_TAG} ---"
gcloud  builds submit \
  --tag "${IMAGE_TAG}" \
  . || { echo "Cloud Build failed!"; exit 1; }

echo "Cloud Build successful. Image tagged as ${IMAGE_TAG}"

# 4. Deploy to Cloud Run
echo "--- 4.  Starting Cloud Run Deployment ---"
gcloud run deploy "${CLOUD_RUN_SERVICE_NAME}" \
  --image "${IMAGE_TAG}" \
  --platform managed \
  --region "${GCP_REGION}" \
  --allow-unauthenticated \
  --add-cloudsql-instances "${CLOUD_SQL_INSTANCE_CONNECTION_NAME}" \
  --set-env-vars "DB_USER=${DB_USER}, \
                  DB_NAME=${DB_NAME}, \
		  INSTANCE_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}, \
		  CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}, \
		  GOOGLE_CLOUD_PROJECT_ID=${GOOGLE_CLOUD_PROJECT_ID}, \
		  DOCUMENT_AI_LOCATION=${DOCUMENT_AI_LOCATION}, \
		  DOCUMENT_AI_PROCESSOR_ID=${DOCUMENT_AI_PROCESSOR_ID}, \
		  BASE_URL=${BASE_URL}, \
                  GCS_BUCKET_NAME=${GCS_BUCKET_NAME}, \
                  MAILGUN_DOMAIN=${MAILGUN_DOMAIN}, \
                  MAILGUN_HOST=${MAILGUN_DOMAIN}, \
                  MAILGUN_REPLY_TO=${MAILGUN_REPLY_TO}, \
		  STRIPE_PRICE_ID=${STRIPE_PRICE_ID}" \
    --set-secrets "DB_PASSWORD=${DB_PASSWORD_SECRET_NAME},  \
                  MAILGUN_API_KEY=${MAILGUN_API_SECRET_NAME},  \
                  STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}"

if [ $? -ne 0 ]; then
    echo "Cloud Run deployment failed!"
    exit 1
fi

echo "Cloud Run deployment successful!"

# 5. Get and Display Service URL
echo "--- 5.  Get and Display Service URL ---"
echo "Service URL:"
SERVICE_URL=$(gcloud run services describe "${CLOUD_RUN_SERVICE_NAME}" \
    --platform managed \
    --region "${GCP_REGION}" \
    --format="value(status.url)")
echo "${SERVICE_URL}"

# 6. Final Cleanup (no manual password input to clean up now)
#unset DB_PASS # Unset the variable just in case
echo "Deployment script finished."
