#!/usr/bin/env bash
# ==============================================================================
# deploy_cloud_run.sh — Automated Google Cloud Run Deployment Script (POSIX Bash)
# ==============================================================================
# Cross-platform deployment for Linux, macOS, and Google Cloud Shell
# ==============================================================================

set -euo pipefail

REGION="${1:-asia-south1}"
SERVICE_NAME="${2:-veri-byte-backend}"
PROJECT_ID="${3:-}"
CORS_ORIGIN="${4:-}"

echo "============================================================"
echo "  Veri-Byte Backend -> Google Cloud Run Deployment (POSIX)  "
echo "============================================================"

# 1. Check if gcloud CLI is installed
if ! command -v gcloud &> /dev/null; then
    echo "[!] Error: 'gcloud' CLI is not found on your system PATH."
    echo "    Install it via: https://cloud.google.com/sdk/docs/install"
    echo "    Or execute directly inside Google Cloud Shell (https://shell.cloud.google.com)."
    exit 1
fi

# 2. Check gcloud auth
echo "[*] Verifying Google Cloud authentication..."
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || true)
if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo "[!] No active GCP account detected. Initiating login..."
    gcloud auth login
else
    echo "[+] Logged in as: $ACTIVE_ACCOUNT"
fi

# 3. Project configuration
if [ -z "$PROJECT_ID" ]; then
    CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
    if [ -z "$CURRENT_PROJECT" ] || [ "$CURRENT_PROJECT" = "(unset)" ]; then
        read -rp "Enter your Google Cloud Project ID (e.g. veri-byte-prod): " PROJECT_ID
    else
        PROJECT_ID="$CURRENT_PROJECT"
    fi
fi

echo "[+] Using Project: $PROJECT_ID"
echo "[+] Using Region:  $REGION (Mumbai)"
gcloud config set project "$PROJECT_ID"

# 4. CORS Origin Configuration (Strict Production Security)
if [ -z "$CORS_ORIGIN" ]; then
    echo ""
    echo "[*] CORS Security Policy: Production requires an explicit Vercel domain."
    read -rp "Enter your Vercel frontend domain (e.g. https://veri-byte.vercel.app): " CORS_ORIGIN
fi

if [ -z "$CORS_ORIGIN" ] || [ "$CORS_ORIGIN" = "*" ]; then
    echo "[!] Error: Permissive wildcard '*' and empty origins are strictly prohibited in production."
    exit 1
fi
# Strip trailing slash
CORS_ORIGIN="${CORS_ORIGIN%/}"
echo "[+] Authorized CORS Origin: $CORS_ORIGIN"

# 5. Enable required GCP APIs
echo "[*] Ensuring required GCP APIs are enabled..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# 6. Build and Deploy to Cloud Run from source
echo "[*] Deploying $SERVICE_NAME to Cloud Run from source..."
echo "    (Source is filtered using .gcloudignore to skip local venv & node_modules)"

gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --memory 4Gi \
  --cpu 2 \
  --concurrency 1 \
  --timeout 300 \
  --allow-unauthenticated \
  --set-env-vars "ENABLE_NEURAL_DEEPFAKE=true,CORS_ORIGINS=$CORS_ORIGIN"

# 6. Retrieve Service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format="value(status.url)")

echo ""
echo "============================================================"
echo "  SUCCESS! Cloud Run Service Deployed Successfully!         "
echo "============================================================"
echo "Backend URL: $SERVICE_URL"

# 7. Health Check Verification with Loud Error Handling
echo "[*] Pinging health endpoint: $SERVICE_URL/api/health ..."
HEALTH_TMP=$(mktemp)
HTTP_CODE=$(curl -s -o "$HEALTH_TMP" -w "%{http_code}" --max-time 60 "$SERVICE_URL/api/health" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo "[+] Health check PASSED! Service is responsive and initialized."
    cat "$HEALTH_TMP"
    echo ""
elif [ "$HTTP_CODE" = "403" ]; then
    echo "[!] CRITICAL: HTTP 403 Forbidden. Cloud Run rejected unauthenticated traffic."
    echo "    Fix: Verify that --allow-unauthenticated was permitted by your GCP organization policy."
elif [ "$HTTP_CODE" = "500" ] || [ "$HTTP_CODE" = "502" ] || [ "$HTTP_CODE" = "503" ]; then
    echo "[!] CRITICAL: HTTP $HTTP_CODE Internal Error. Container crashed during startup."
    echo "    Inspect live crash logs:"
    echo "      gcloud run services logs read $SERVICE_NAME --region $REGION --limit 40"
else
    echo "[!] Health check request failed with HTTP $HTTP_CODE."
    echo "    Inspect logs:"
    echo "      gcloud run services logs read $SERVICE_NAME --region $REGION --limit 40"
fi
rm -f "$HEALTH_TMP"

echo ""
echo "============================================================"
echo "  NEXT STEPS FOR VERCEL FRONTEND:                          "
echo "============================================================"
echo "1. Go to Vercel Dashboard -> Project Settings -> Environment Variables"
echo "2. Set VITE_API_URL=$SERVICE_URL (no trailing slash)"
echo "3. Trigger a redeploy on Vercel."
echo "4. Lock down CORS:"
echo "   gcloud run services update $SERVICE_NAME --region $REGION --update-env-vars CORS_ORIGINS=https://your-project.vercel.app"
echo "============================================================"
