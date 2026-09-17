# ==============================================================================
# deploy_cloud_run.ps1 — Automated Google Cloud Run Deployment Script
# ==============================================================================
# Veri-Byte Forensic Document Inspector Cloud Backend Deployment
# ==============================================================================

param(
    [string]$ProjectId = "",
    [string]$Region = "asia-south1",
    [string]$ServiceName = "veri-byte-backend"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Veri-Byte Backend -> Google Cloud Run Deployment Assistant " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Check if gcloud is installed
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Error: 'gcloud' CLI is not found on your system PATH." -ForegroundColor Red
    Write-Host "    Install it using:" -ForegroundColor Yellow
    Write-Host "      winget install Google.CloudSDK" -ForegroundColor White
    Write-Host "    Then restart your PowerShell terminal and re-run this script." -ForegroundColor Yellow
    exit 1
}

# 2. Check gcloud auth
Write-Host "`n[*] Verifying Google Cloud authentication..." -ForegroundColor Gray
$account = (gcloud auth list --filter=status:ACTIVE --format="value(account)") 2>$null
if (-not $account) {
    Write-Host "[!] No active Google Cloud account logged in. Initiating login..." -ForegroundColor Yellow
    gcloud auth login
} else {
    Write-Host "[+] Logged in as: $account" -ForegroundColor Green
}

# 3. Project Configuration
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    $currentProj = (gcloud config get-value project 2>$null)
    if ([string]::IsNullOrWhiteSpace($currentProj) -or $currentProj -eq "(unset)") {
        $ProjectId = Read-Host "Enter your Google Cloud Project ID (e.g. veri-byte-prod)"
    } else {
        $ProjectId = $currentProj
    }
}

Write-Host "[+] Using Project: $ProjectId" -ForegroundColor Green
Write-Host "[+] Using Region:  $Region (Mumbai)" -ForegroundColor Green
gcloud config set project $ProjectId

# 4. Enable Required GCP APIs
Write-Host "`n[*] Ensuring required GCP APIs are enabled..." -ForegroundColor Gray
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# 5. Build and Deploy to Cloud Run
Write-Host "`n[*] Deploying $ServiceName to Cloud Run from source..." -ForegroundColor Cyan
Write-Host "    (Source is filtered using .gcloudignore to skip local venv & node_modules)" -ForegroundColor DarkGray

gcloud run deploy $ServiceName `
  --source . `
  --region $Region `
  --memory 4Gi `
  --cpu 2 `
  --concurrency 1 `
  --timeout 300 `
  --allow-unauthenticated `
  --set-env-vars "ENABLE_NEURAL_DEEPFAKE=true,CORS_ORIGINS=*"

# 6. Retrieve Service URL
$ServiceUrl = (gcloud run services describe $ServiceName --region $Region --format="value(status.url)")

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  SUCCESS! Cloud Run Service Deployed Successfully!         " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Backend URL: $ServiceUrl" -ForegroundColor Cyan

# 7. Health Check Verification
Write-Host "`n[*] Pinging health endpoint: $ServiceUrl/api/health ..." -ForegroundColor Gray
try {
    $healthRes = Invoke-RestMethod -Uri "$ServiceUrl/api/health" -Method Get -TimeoutSec 60
    Write-Host "[+] Health check PASSED! Service is responsive and initialized." -ForegroundColor Green
    $healthRes | ConvertTo-Json -Depth 3 | Write-Host -ForegroundColor DarkGray
} catch {
    Write-Host "`n[!] CRITICAL: Health check request failed!" -ForegroundColor Red
    
    $statusCode = $null
    if ($_.Exception.Response) {
        $statusCode = [int]$_.Exception.Response.StatusCode
    }
    
    if ($statusCode -eq 403) {
        Write-Host "    HTTP 403 Forbidden: Cloud Run is rejecting unauthenticated traffic." -ForegroundColor Red
        Write-Host "    Fix: Verify that --allow-unauthenticated was permitted by your GCP organization policy." -ForegroundColor Yellow
    } elseif ($statusCode -eq 500 -or $statusCode -eq 502 -or $statusCode -eq 503) {
        Write-Host "    HTTP $statusCode Error: The container crashed during startup (e.g. OOM, import failure, or missing dependency)." -ForegroundColor Red
        Write-Host "    View live container crash logs:" -ForegroundColor Yellow
        Write-Host "      gcloud run services logs read $ServiceName --region $Region --limit 40" -ForegroundColor White
    } else {
        Write-Host "    Error detail: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "    To diagnose container status, inspect logs:" -ForegroundColor Yellow
        Write-Host "      gcloud run services logs read $ServiceName --region $Region --limit 40" -ForegroundColor White
    }
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  NEXT STEPS FOR VERCEL FRONTEND:                          " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "1. Go to your Vercel Dashboard -> Project Settings -> Environment Variables" -ForegroundColor White
Write-Host "2. Set or update:" -ForegroundColor Yellow
Write-Host "   Key:   VITE_API_URL" -ForegroundColor White
Write-Host "   Value: $ServiceUrl" -ForegroundColor Green
Write-Host "3. Trigger a redeploy in Vercel so Vite bakes in the new API URL." -ForegroundColor White
Write-Host "4. Lock down CORS once Vercel is live:" -ForegroundColor Yellow
Write-Host "   gcloud run services update $ServiceName --region $Region --update-env-vars CORS_ORIGINS=https://your-project.vercel.app" -ForegroundColor DarkCyan
Write-Host "============================================================`n" -ForegroundColor Cyan
