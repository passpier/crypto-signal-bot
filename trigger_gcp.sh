#!/bin/bash

# Trigger crypto-signal-bot on Google Cloud Run
# Usage: ./trigger_gcp.sh <project-id> [service-name] [region]
# Example: ./trigger_gcp.sh crypto-signal-bot-prod crypto-signal-bot asia-east1

set -e

PROJECT_ID="${1:-crypto-signal-bot-prod}"
SERVICE_NAME="${2:-crypto-signal-bot}"
REGION="${3:-asia-east1}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install it first:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set project
gcloud config set project "$PROJECT_ID" > /dev/null

# Get the service URL
echo "Retrieving service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" \
    --format 'value(status.url)' 2>/dev/null)

if [ -z "$SERVICE_URL" ]; then
    echo "❌ Could not find service: $SERVICE_NAME"
    echo "Please make sure the service exists and is deployed in region: $REGION"
    exit 1
fi

echo "Service URL: $SERVICE_URL"
echo ""

# Get an identity token for authentication
echo "Generating authentication token..."
TOKEN=$(gcloud auth print-identity-token 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ Could not generate authentication token"
    echo "Make sure you're authenticated: gcloud auth login"
    exit 1
fi

# Trigger the bot
echo "Triggering bot execution..."
echo ""

RESPONSE=$(curl -s -X POST "${SERVICE_URL}/trigger" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -w "\n%{http_code}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

# Parse and display response
if [ "$HTTP_CODE" -eq 200 ]; then
    echo "✓ Bot execution triggered successfully!"
    echo ""
    echo "Response:"
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
    echo "❌ Failed to trigger bot (HTTP $HTTP_CODE)"
    echo ""
    echo "Response:"
    echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
    exit 1
fi

echo ""
echo "View logs with:"
echo "  gcloud run logs read --service=$SERVICE_NAME --limit=50"
