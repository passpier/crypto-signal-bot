#!/bin/bash
# 新增或更新 Cloud Scheduler job
set -e
source ./config_gcp.sh

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)')

# 若 job 已存在就 update，不整個砍掉重建
if gcloud scheduler jobs describe "$SCHEDULER_JOB_NAME" --location "$REGION" &>/dev/null; then
  gcloud scheduler jobs update http "$SCHEDULER_JOB_NAME" \
    --location "$REGION" \
    --schedule "$CRON_SCHEDULE" \
    --time-zone "$TIMEZONE"
  echo "✓ Scheduler job updated"
else
  gcloud scheduler jobs create http "$SCHEDULER_JOB_NAME" \
    --location "$REGION" \
    --schedule "$CRON_SCHEDULE" \
    --time-zone "$TIMEZONE" \
    --http-method POST \
    --uri "${SERVICE_URL}/trigger" \
    --oidc-service-account-email "$SERVICE_ACCOUNT" \
    --oidc-token-audience "$SERVICE_URL"
  echo "✓ Scheduler job created"
fi
