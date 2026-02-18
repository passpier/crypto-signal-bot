#!/bin/bash

# Deploy crypto-signal-bot to Google Cloud Run with Cloud Scheduler integration
# Usage: ./deploy_gcp.sh <project-id> <region> <service-name>
# Example: ./deploy_gcp.sh crypto-signal-bot-prod asia-east1 crypto-signal-bot

set -e

# Configuration
PROJECT_ID="${1:-crypto-signal-bot-prod}"
REGION="${2:-asia-east1}"
SERVICE_NAME="${3:-crypto-signal-bot}"
SCHEDULER_JOB_NAME="${SERVICE_NAME}-scheduler"
SCHEDULER_SA_NAME="${SERVICE_NAME}-scheduler-sa"
CRON_SCHEDULE="${CRON_SCHEDULE:-0 0 * * *}"  # Daily at midnight UTC
TIMEZONE="${TIMEZONE:-Asia/Taipei}"

echo "==============================================="
echo "Deploying Crypto Signal Bot to Cloud Run"
echo "==============================================="
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo "Scheduler: $SCHEDULER_JOB_NAME"
echo "Schedule: $CRON_SCHEDULE (Timezone: $TIMEZONE)"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install it first:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set project
echo "Setting GCP project..."
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Deploy to Cloud Run
echo ""
echo "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --platform managed \
    --region "$REGION" \
    --timeout 600 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 1 \
    --no-allow-unauthenticated

# Get the service URL
echo ""
echo "Retrieving service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" \
    --format 'value(status.url)')

echo "✓ Service deployed: $SERVICE_URL"

# Set up Cloud Scheduler job
echo ""
echo "Setting up Cloud Scheduler job..."

# Create or get scheduler service account
SERVICE_ACCOUNT="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Check if service account exists
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT" &> /dev/null; then
    echo "Using existing service account: $SERVICE_ACCOUNT"
else
    echo "Creating scheduler service account: $SERVICE_ACCOUNT"
    gcloud iam service-accounts create "$SCHEDULER_SA_NAME" \
        --display-name "Service account for Cloud Scheduler to invoke Cloud Run"
fi

# Grant Cloud Run Invoker permission
echo "Granting Cloud Run Invoker role..."
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
    --region "$REGION" \
    --member "serviceAccount:$SERVICE_ACCOUNT" \
    --role "roles/run.invoker" \
    --quiet

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to grant Cloud Run Invoker role to $SERVICE_ACCOUNT"
    exit 1
fi

# Delete existing scheduler job if it exists
if gcloud scheduler jobs describe "$SCHEDULER_JOB_NAME" --location "$REGION" &> /dev/null; then
    echo "Deleting existing scheduler job..."
    gcloud scheduler jobs delete "$SCHEDULER_JOB_NAME" \
        --location "$REGION" \
        --quiet
fi

# Create new scheduler job
gcloud scheduler jobs create http "$SCHEDULER_JOB_NAME" \
    --location "$REGION" \
    --schedule "$CRON_SCHEDULE" \
    --timezone "$TIMEZONE" \
    --http-method POST \
    --uri "${SERVICE_URL}/trigger" \
    --oidc-service-account-email "$SERVICE_ACCOUNT" \
    --oidc-token-audience "$SERVICE_URL"

echo "✓ Cloud Scheduler job created: $SCHEDULER_JOB_NAME"

# Display summary
echo ""
echo "==============================================="
echo "✓ Deployment Complete!"
echo "==============================================="
echo ""
echo "Next steps:"
echo "1. Set environment variables:"
echo "   gcloud run services update $SERVICE_NAME \\"
echo "     --region=$REGION \\"
echo "     --update-env-vars TELEGRAM_TOKEN=your_token,TELEGRAM_CHAT_ID=your_chat_id,GEMINI_API_KEY=your_key"
echo ""
echo "2. Manually trigger the bot (using Cloud Scheduler):"
echo "   gcloud scheduler jobs run $SCHEDULER_JOB_NAME --location=$REGION"
echo ""
echo "3. Monitor logs:"
echo "   gcloud run services logs read $SERVICE_NAME --limit=100"
echo ""
echo "4. Check scheduler job status:"
echo "   gcloud scheduler jobs describe $SCHEDULER_JOB_NAME --location=$REGION"
echo ""
