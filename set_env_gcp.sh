#!/bin/bash
# 更新 Cloud Run 的 env vars（key 異動時）
set -e
source ./config_gcp.sh

gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --update-env-vars \
    TELEGRAM_TOKEN="${TELEGRAM_TOKEN:?required}", \
    TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:?required}", \
    GEMINI_API_KEY="${GEMINI_API_KEY:?required}"

echo "✓ Env vars updated"
