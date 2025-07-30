#!/bin/bash

# --- Configuration Variables ---
# IMPORTANT: Replace these with your actual values.
# For DB_PASS, consider using a secure method like prompting or a secrets manager
# instead of hardcoding if this script will be shared or committed to source control.

CLOUD_RUN_SERVICE_NAME="workschedule-api" # Your chosen Cloud Run service name
GCP_PROJECT_ID="work-schedule-cloud"     # Your Google Cloud Project ID
GCP_REGION="us-central1"                 # Your desired Cloud Run and Cloud SQL region

# Cloud SQL Instance Details
CLOUD_SQL_INSTANCE_CONNECTION_NAME="work-schedule-cloud:us-central1:workschedule-db"
DB_USER="postgres"                       # Your Cloud SQL database username
DB_NAME="workschedule_db"                # Your Cloud SQL database name

# Prompt for database password securely
read -s -p "Enter Cloud SQL DB password for ${DB_USER}: " DB_PASS
echo # Move to a new line after password input

# --- Build the Docker Image ---
echo "--- Starting Cloud Build for Docker Image ---"
gcloud builds submit \
  --tag "gcr.io/${GCP_PROJECT_ID}/workschedule-cloud-app" \
  . || { echo "Cloud Build failed!"; exit 1; } # Exit if build fails

echo "Cloud Build successful. Image tagged as gcr.io/${GCP_PROJECT_ID}/workschedule-cloud-app"

# --- Deploy to Cloud Run ---
echo "--- Starting Cloud Run Deployment ---"
gcloud run deploy "${CLOUD_RUN_SERVICE_NAME}" \
  --image "gcr.io/${GCP_PROJECT_ID}/workschedule-cloud-app" \
  --platform managed \
  --region "${GCP_REGION}" \
  --allow-unauthenticated \
  --add-cloudsql-instances "${CLOUD_SQL_INSTANCE_CONNECTION_NAME}" \
  --set-env-vars "DB_USER=${DB_USER},DB_PASS=${DB_PASS},DB_NAME=${DB_NAME},INSTANCE_CONNECTION_NAME=${CLOUD_SQL_INSTANCE_CONNECTION_NAME}" \
  --project "${GCP_PROJECT_ID}" || { echo "Cloud Run deployment failed!"; exit 1; } # Exit if deployment fails

echo "Cloud Run deployment successful!"
echo "Service URL (check Cloud Run console if not displayed here):"
gcloud run services describe "${CLOUD_RUN_SERVICE_NAME}" --platform managed --region "${GCP_REGION}" --format="value(status.url)"

# Clear password from shell history (best effort)
history -d $((HISTCMD-1))
unset DB_PASS

echo "Deployment script finished."
