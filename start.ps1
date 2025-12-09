# Launch RB Assist NiceGUI UI
# - Activates the local venv
# - Starts the UI on the default port (8080)
# If the port is busy, uncomment the stop-port block below.

$ErrorActionPreference = "Stop"

# Uncomment to free port 8080 if something is stuck:
# Get-NetTCPConnection -LocalPort 8080 -State Listen, Established |
#   ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

Write-Host "Activating virtual environment..." -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

# Quiet TensorFlow/oneDNN info and resampy/pkg_resources warning
$env:TF_CPP_MIN_LOG_LEVEL = "2"
$env:TF_ENABLE_ONEDNN_OPTS = "0"
$env:PYTHONWARNINGS = "ignore:pkg_resources is deprecated as an API:UserWarning"

Write-Host "Starting rbassist UI on http://localhost:8080" -ForegroundColor Green
rbassist ui
