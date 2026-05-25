#!/bin/bash
# GCP
CLOUD_RUN_SERVICE_NAME="workschedule-cloud-app"
GCP_PROJECT_ID="work-schedule-cloud"
GCP_REGION="us-central1"

# --- Verify Authenticated User ---
echo "--- Verifying Authenticated gcloud User ---"
AUTH_USER=$(gcloud config get-value account)
echo "Authenticated as: ${AUTH_USER}"
echo "----------------------------------------"

# Other config
#BASE_URL="https://www.myschedule.cloud"
BASE_URL="https://myschedule.cloud"
GCS_BUCKET_NAME="work-schedule-cloud"

GOOGLE_CLOUD_PROJECT_ID="work-schedule-cloud"

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
IMAGE_TAG="gcr.io/${GCP_PROJECT_ID}/workschedule-cloud-app:$(date +%s)"
echo "--- Image TAG = ${IMAGE_TAG} ---"
gcloud builds submit \
  --tag "${IMAGE_TAG}" \
  . || { echo "Cloud Build failed!"; exit 1; }
echo "Cloud Build successful. Image tagged as ${IMAGE_TAG}"

echo "--- 4. Starting Cloud Run Deployment ---"
gcloud run deploy "${CLOUD_RUN_SERVICE_NAME}" \
  --image "${IMAGE_TAG}" \
  --platform managed \
  --region "${GCP_REGION}" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT_ID=${GOOGLE_CLOUD_PROJECT_ID}, \
                  BASE_URL=${BASE_URL}, \
                  GCS_BUCKET_NAME=${GCS_BUCKET_NAME}" \
  --set-secrets "STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY_NAME}:latest, \
                 STRIPE_PRICE_ID=${STRIPE_PRICE_ID_NAME}:latest, \
                 STRIPE_PUBLISHABLE_KEY=${STRIPE_PUBLISHABLE_KEY_NAME}:latest, \
                 MAGIC_LINK_SECRET=magic-link-secret:latest, \
                 ANTHROPIC_API_KEY=anthropic-api-key:latest"

if [ $? -ne 0 ]; then
    echo "Cloud Run deployment failed!"
    exit 1
fi
echo "Cloud Run deployment successful!"

# 5. Get and Display Service URL
echo "--- 5. Get and Display Service URL ---"
SERVICE_URL=$(gcloud run services describe "${CLOUD_RUN_SERVICE_NAME}" \
    --platform managed \
    --region "${GCP_REGION}" \
    --format="value(status.url)")
echo "Service URL: ${SERVICE_URL}"

echo "Deployment script finished."
