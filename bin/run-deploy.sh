#!/bin/bash


# GCP
CLOUD_RUN_SERVICE_NAME="workschedule-api" # Your chosen Cloud Run service name
GCP_PROJECT_ID="work-schedule-cloud"     # Your Google Cloud Project ID
GCP_REGION="us-central1"                 # Your desired Cloud Run and Cloud SQL region

# --- Verify Authenticated User ---
echo "--- Verifying Authenticated gcloud User ---"
AUTH_USER=$(gcloud config get-value account)
echo "Authenticated as: ${AUTH_USER}"
echo "----------------------------------------"

# Cloud Run Secret Manager variable names
MAILGUN_API_SECRET_NAME="workschedule-mailgun-api-key"

# Other config
BASE_URL="https://www.myschedule.cloud"
GCS_BUCKET_NAME="work-schedule-cloud"
MAILGUN_REPLY_TO="reply@myschedule.cloud"
MAILGUN_DOMAIN="mg.myschedule.cloud"

# Document AI and pdf processing
GOOGLE_CLOUD_PROJECT_ID="work-schedule-cloud"
GOOGLE_APPLICATION_CREDENTIALS="/instance/service-account.json"
PROJECT_ID="work-schedule-cloud"
DOCUMENT_AI_LOCATION="us"
LOCATION="us"
DOCUMENT_AI_PROCESSOR_ID="fe0baaa28beedbe9"
PROCESSOR_ID="fe0baaa28beedbe9"

# --- Main Script Execution ---


# --- Input Argument for environment (test or live) ---
ENV=$1
if [[ "$ENV" != "test" && "$ENV" != "live" ]]; then
    echo "Usage: $0 [test|live]"
    exit 1
fi
echo "--- Deploying to ${ENV} environment ---"

# --- Dynamically set Stripe secret and price names based on environment ---
STRIPE_SECRET_KEY_NAME="stripe-${ENV}-secret-key"
STRIPE_PUBLISHABLE_KEY_NAME="stripe-${ENV}-publishable-key"
STRIPE_PRICE_ID_NAME="stripe-${ENV}-price-id"

echo "--- 3. Starting Cloud Build for Docker Image ---"
IMAGE_TAG="gcr.io/${GCP_PROJECT_ID}/workschedule-cloud-app"
echo "--- Image TAG = ${IMAGE_TAG} ---"
gcloud  builds submit \
  --tag "${IMAGE_TAG}" \
  . || { echo "Cloud Build failed!"; exit 1; }

echo "Cloud Build successful. Image tagged as ${IMAGE_TAG}"

echo "--- 4. Starting Cloud Run Deployment ---"

gcloud run deploy "${CLOUD_RUN_SERVICE_NAME}" \
  --image "${IMAGE_TAG}" \
  --platform managed \
  --region "${GCP_REGION}" \
  --allow-unauthenticated \
  --add-cloudsql-instances "${CLOUD_SQL_INSTANCE_CONNECTION_NAME}" \
  --set-env-vars " INSTANCE_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}, \
                  CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}, \
                  GOOGLE_CLOUD_PROJECT_ID=${GOOGLE_CLOUD_PROJECT_ID}, \
                  GOOGLE_APPLICATION_CREDENTIALS=${GOOGLE_APPLICATION_CREDENTIALS}, \
                  DOCUMENT_AI_LOCATION=${DOCUMENT_AI_LOCATION}, \
                  DOCUMENT_AI_PROCESSOR_ID=${DOCUMENT_AI_PROCESSOR_ID}, \
                  BASE_URL=${BASE_URL}, \
                  GCS_BUCKET_NAME=${GCS_BUCKET_NAME}, \
                  MAILGUN_DOMAIN=${MAILGUN_DOMAIN}, \
                  MAILGUN_HOST=${MAILGUN_DOMAIN}, \
                  MAILGUN_REPLY_TO=${MAILGUN_REPLY_TO}" \
  --set-secrets " MAILGUN_API_KEY=${MAILGUN_API_SECRET_NAME}:latest, \
                 STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY_NAME}:latest, \
                 STRIPE_PRICE_ID=${STRIPE_PRICE_ID_NAME}:latest, \
                 STRIPE_PUBLISHABLE_KEY=${STRIPE_PUBLISHABLE_KEY_NAME}:latest"

if [ $? -ne 0 ]; then
    echo "Cloud Run deployment failed!"
    exit 1
fi

echo "Cloud Run deployment successful!"

# 5. Get and Display Service URL
echo "--- 5. Get and Display Service URL ---"
echo "Service URL:"
SERVICE_URL=$(gcloud run services describe "${CLOUD_RUN_SERVICE_NAME}" \
    --platform managed \
    --region "${GCP_REGION}" \
    --format="value(status.url)")
echo "${SERVICE_URL}"

# 6. Final Cleanup
echo "Deployment script finished."
