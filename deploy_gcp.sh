#!/bin/bash
# 首次部署：建立所有 GCP 基礎設施
set -e
source ./config_gcp.sh  # 共用設定

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com

# 建 Service Account
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" &>/dev/null; then
  gcloud iam service-accounts create "$SCHEDULER_SA_NAME" \
    --display-name "Scheduler SA for Cloud Run"
fi

# 部署 Cloud Run
gcloud run deploy "$SERVICE_NAME" \
  --source . --platform managed --region "$REGION" \
  --timeout 600 --memory 512Mi --cpu 1 \
  --min-instances 0 --max-instances 1 \
  --no-allow-unauthenticated

# 取得 URL 後授權 IAM
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)')
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region "$REGION" \
  --member "serviceAccount:$SERVICE_ACCOUNT" \
  --role "roles/run.invoker" --quiet

echo "✓ Deploy done: $SERVICE_URL"
