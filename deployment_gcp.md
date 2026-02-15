# Google Cloud Run Deployment Guide

This guide explains how to deploy the crypto-signal-bot to Google Cloud Run with automated scheduling via Cloud Scheduler.

## Architecture Overview

The deployment uses:
- **Google Cloud Run**: Serverless container runtime for the Flask HTTP server
- **Cloud Scheduler**: Managed cron scheduler to trigger the bot daily
- **Cloud Logging**: Centralized logging for monitoring and debugging
- **Cloud Build**: Automatic Docker image building and deployment

## Prerequisites

1. **Google Cloud Account**
   - Free tier includes 180,000 vCPU-seconds per month (~daily executions cost $0)
   - Cloud Run: 2M monthly requests included
   - Cloud Scheduler: 3 free jobs

2. **gcloud CLI**
   ```bash
   # Install gcloud SDK
   # See: https://cloud.google.com/sdk/docs/install

   # Verify installation
   gcloud --version

   # Authenticate
   gcloud auth login
   ```

3. **Credentials**
   - `TELEGRAM_TOKEN`: From @BotFather on Telegram
   - `TELEGRAM_CHAT_ID`: From @userinfobot on Telegram
   - `GEMINI_API_KEY`: From [Google AI Studio](https://aistudio.google.com/) (optional)

## Setup Instructions

### Step 1: Create a GCP Project

```bash
# Create new project
gcloud projects create crypto-signal-bot-prod

# List projects to confirm
gcloud projects list

# Set as active project
gcloud config set project crypto-signal-bot-prod
```

### Step 2: Enable Required APIs

```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### Step 3: Deploy to Cloud Run

```bash
# Make deployment script executable
chmod +x deploy_gcp.sh

# Deploy with default settings
./deploy_gcp.sh crypto-signal-bot-prod us-central1 crypto-signal-bot

# Or customize:
CRON_SCHEDULE="0 9 * * *" TIMEZONE="America/New_York" \
  ./deploy_gcp.sh crypto-signal-bot-prod us-central1 crypto-signal-bot
```

The script will:
1. Enable required APIs
2. Build and deploy Docker container to Cloud Run
3. Create Cloud Scheduler job for daily execution
4. Output the service URL and next steps

### Step 4: Configure Environment Variables

```bash
gcloud run services update crypto-signal-bot \
  --region=us-central1 \
  --update-env-vars \
    TELEGRAM_TOKEN=your_actual_token,\
    TELEGRAM_CHAT_ID=your_actual_chat_id,\
    GEMINI_API_KEY=your_actual_gemini_key
```

Or set them individually:
```bash
gcloud run services update crypto-signal-bot \
  --region=us-central1 \
  --set-env-vars TELEGRAM_TOKEN=your_token
```

### Step 5: Verify Deployment

**Check health endpoint:**
```bash
SERVICE_URL=$(gcloud run services describe crypto-signal-bot \
  --region=us-central1 --format='value(status.url)')

curl $SERVICE_URL/health
# Expected: {"status":"healthy","service":"crypto-signal-bot"}
```

**Manually trigger the bot:**
```bash
./trigger_gcp.sh crypto-signal-bot-prod crypto-signal-bot us-central1
```

**View logs:**
```bash
# Last 50 logs
gcloud run logs read --service=crypto-signal-bot --limit=50

# Real-time logs
gcloud run logs read --service=crypto-signal-bot --follow

# Filter by severity
gcloud run logs read --service=crypto-signal-bot --level=ERROR
```

## Configuration

### Schedule (Cloud Scheduler)

Default: `0 0 * * *` (Daily at midnight UTC)

To modify the schedule:
```bash
# Describe current job
gcloud scheduler jobs describe crypto-signal-bot-scheduler \
  --location=us-central1

# Update schedule (5-field Unix CRON format)
gcloud scheduler jobs update http crypto-signal-bot-scheduler \
  --location=us-central1 \
  --schedule="0 9 * * *"  # 9 AM UTC

# Common schedules:
# 0 0 * * *     = Midnight UTC
# 0 9 * * *     = 9 AM UTC
# 0 0 * * 1     = Mondays midnight UTC
# 0,6,12,18 * * * *  = Every 6 hours
```

### Timezone

Default: `Asia/Taipei` (UTC+8)

Change timezone:
```bash
gcloud scheduler jobs update http crypto-signal-bot-scheduler \
  --location=us-central1 \
  --timezone="America/New_York"
```

### Resource Allocation

Current settings (can be adjusted):
- **Memory**: 512 MB (sufficient for technical analysis + Gemini API)
- **CPU**: 1 vCPU
- **Timeout**: 600 seconds (10 minutes)
- **Max instances**: 1 (prevents concurrent executions)
- **Min instances**: 0 (serverless - pay per execution)

Adjust resources:
```bash
gcloud run deploy crypto-signal-bot \
  --region=us-central1 \
  --memory 1Gi \
  --cpu 2 \
  --timeout 900
```

## Monitoring

### View Service Details

```bash
gcloud run services describe crypto-signal-bot --region=us-central1
```

### Monitor Execution Metrics

```bash
# View Cloud Run metrics in console
gcloud monitoring metrics-descriptors list --filter="service:run"

# Check recent executions
gcloud scheduler jobs describe crypto-signal-bot-scheduler --location=us-central1
```

### Set Up Alerts (Optional)

Create a Cloud Monitoring alert for high error rates:
```bash
# Via Google Cloud Console:
# 1. Go to Monitoring > Alerting > Create Policy
# 2. Choose metric: "Cloud Run Request Count"
# 3. Filter by: resource.service_name = "crypto-signal-bot"
# 4. Condition: error_count > 0
# 5. Add notification channel (Email, Slack, etc.)
```

## Troubleshooting

### Issue: Scheduler job fails to trigger

**Symptom**: Error about OIDC token, service account, or permissions

**Solution**:
```bash
# Verify service account exists
gcloud iam service-accounts list

# Grant Cloud Run Invoker role manually
gcloud run services add-iam-policy-binding crypto-signal-bot \
  --region=us-central1 \
  --member="serviceAccount:PROJECT_ID@appspot.gserviceaccount.com" \
  --role="roles/run.invoker"
```

### Issue: Bot doesn't send Telegram messages

**Symptom**:
- Health check passes
- Logs show successful execution
- No Telegram message received

**Solution**:
```bash
# Verify environment variables are set
gcloud run services describe crypto-signal-bot \
  --region=us-central1 --format=json | jq '.spec.template.spec.containers[0].env'

# Test with manual trigger
./trigger_gcp.sh crypto-signal-bot-prod crypto-signal-bot us-central1

# Check logs for Telegram API errors
gcloud run logs read --service=crypto-signal-bot --level=ERROR
```

### Issue: "API not enabled" error during deployment

**Solution**:
```bash
# Enable APIs manually
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Re-run deployment script
./deploy_gcp.sh crypto-signal-bot-prod us-central1 crypto-signal-bot
```

### Issue: Logs not visible

**Solution**:
```bash
# Ensure logs are being written
gcloud run logs read --service=crypto-signal-bot --limit=100

# Check service status
gcloud run services describe crypto-signal-bot --region=us-central1

# View recent requests
gcloud logging read \
  "resource.type=cloud_run_revision AND \
   resource.labels.service_name=crypto-signal-bot" \
  --limit 20 \
  --format=json | jq '.[] | {timestamp: .timestamp, message: .jsonPayload.message}'
```

## Cost Estimation

**Monthly cost for daily execution:**

| Resource | Usage | Cost |
|----------|-------|------|
| Cloud Run | 30 executions × 120 sec × 512 MB | $0.00 (free tier) |
| Cloud Scheduler | 30 jobs | $0.00 (3 free jobs) |
| Cloud Logging | ~30 MB logs | $0.00 (first 50 GB free) |
| **Total** | | **$0.00** |

As long as daily execution time stays under 10 minutes and Cloud Logging doesn't exceed 50 GB/month, deployment is completely free.

## Cleanup

To remove all resources:

```bash
# Delete Cloud Scheduler job
gcloud scheduler jobs delete crypto-signal-bot-scheduler --location=us-central1

# Delete Cloud Run service
gcloud run services delete crypto-signal-bot --region=us-central1

# Disable APIs (optional)
gcloud services disable run.googleapis.com
gcloud services disable cloudscheduler.googleapis.com
gcloud services disable cloudbuild.googleapis.com

# Delete project (optional)
gcloud projects delete crypto-signal-bot-prod
```

## Advanced Configuration

### Custom Docker Image Registry

To push images to Artifact Registry instead of automatic Cloud Build:

```bash
# Enable Artifact Registry
gcloud services enable artifactregistry.googleapis.com

# Create repository
gcloud artifacts repositories create crypto-signal-bot \
  --repository-format=docker \
  --location=us-central1

# Build and push image
docker build -t us-central1-docker.pkg.dev/PROJECT_ID/crypto-signal-bot/crypto-signal-bot:latest .
docker push us-central1-docker.pkg.dev/PROJECT_ID/crypto-signal-bot/crypto-signal-bot:latest

# Deploy from image
gcloud run deploy crypto-signal-bot \
  --image=us-central1-docker.pkg.dev/PROJECT_ID/crypto-signal-bot/crypto-signal-bot:latest \
  --region=us-central1
```

### Private Service (Authentication Required)

To require authentication for manual triggers:

```bash
# Remove public access
gcloud run services remove-iam-policy-binding crypto-signal-bot \
  --region=us-central1 \
  --member="allUsers" \
  --role="roles/run.invoker"

# Scheduler will still work (uses service account)
```

### Custom Domain

To use a custom domain:

```bash
# Configure custom domain
gcloud run domain-mappings create --service=crypto-signal-bot \
  --domain=botname.example.com

# Follow prompts to update DNS records
```

## See Also

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Scheduler Documentation](https://cloud.google.com/scheduler/docs)
- [Cloud Logging Documentation](https://cloud.google.com/logging/docs)
- [Pricing Calculator](https://cloud.google.com/products/calculator)
