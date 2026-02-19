#!/bin/bash
# 手動觸發 Cloud Run bot
set -e
source ./config_gcp.sh

gcloud config set project "$PROJECT_ID" 2>/dev/null

echo "Retrieving service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --format 'value(status.url)')
echo "Service URL: $SERVICE_URL"

echo "Generating authentication token..."
TOKEN=$(gcloud auth print-identity-token --audiences="$SERVICE_URL")

echo "Triggering bot execution..."
curl -s -X POST "${SERVICE_URL}/trigger" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n"
