#!/bin/bash
# 只重新 build & deploy image，不動 IAM 或 Scheduler
set -e
source ./config_gcp.sh

gcloud run deploy "$SERVICE_NAME" \
  --source . --platform managed --region "$REGION" \
  --no-allow-unauthenticated

echo "✓ Image updated"
