rek<#
Fixer script v2 for rbassist (improved TOML validation).

Usage:
  .\fix_rbassist_install_v2.ps1 -CreateVenv
  .\fix_rbassist_install_v2.ps1 -Extras "ml,stems" -RunStreamlit
#>
param(
    [switch]$CreateVenv = $false,
    [string]$Extras = "",
    [switch]$RunStreamlit = $false
)

function Info($s){ Write-Host $s -ForegroundColor Cyan }
function Err($s){ Write-Host $s -ForegroundColor Red }
function Succ($s){ Write-Host $s -ForegroundColor Green }

$repo = Get-Location
Info "Repo root: $repo"

# Create venv if requested
$venv = Join-Path $repo ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"

if ($CreateVenv) {
    if (-not (Test-Path $venvPy)) {
        Info "Creating virtualenv at $venv..."
        python -m venv $venv
        if (-not (Test-Path $venvPy)) {
            Err "Virtualenv creation failed. Make sure 'python' is on PATH."
            exit 1
        }
        Succ "Virtualenv created."
    } else {
        Info "Virtualenv already exists."
    }
}

# Choose python: venv python preferred
$pythonExe = if (Test-Path $venvPy) { $venvPy } else { (Get-Command python -ErrorAction SilentlyContinue).Source }

if (-not $pythonExe) {
    Err "No python executable found. Install Python 3.10+ or create a venv first."
    exit 1
}
Info "Using Python: $pythonExe"

# Backup pyproject.toml
$pj = Join-Path $repo "pyproject.toml"
if (-not (Test-Path $pj)) {
    Err "pyproject.toml not found in repo root. Aborting."
    exit 1
}
$bak = "$pj.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $pj $bak -Force
Succ "Backed up pyproject.toml → $bak"

# Show first 20 lines for debug
Info "`n--- current pyproject.toml head ---"
Get-Content $pj -TotalCount 20 | ForEach-Object { "{0}: {1}" -f ($global:i = ($global:i + 1) -as [int]), $_ }
Remove-Variable i -ErrorAction SilentlyContinue

# Write a clean pyproject.toml (no BOM)
Info "`nWriting safe pyproject.toml (no BOM)..."
$clean = @'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "rbassist"
version = "0.1.0"
description = "Rekordbox Assist: beatgrid+key helpers, audio similarity, smart crates"
authors = [{ name = "You" }]
readme = "rbassist/readme.txt"
requires-python = ">=3.10"
dependencies = [
  "typer[all]~=0.12",
  "rich~=13.7",
  "numpy~=1.26",
  "librosa~=0.10",
  "soundfile~=0.12",
  "tqdm~=4.66",
  "pandas~=2.2",
  "pyyaml~=6.0.1"
]

[project.optional-dependencies]
stems = ["demucs"]
ml = ["transformers>=4.40", "accelerate>=0.28", "datasets>=2.18"]
audio = ["mutagen>=1.47", "pyloudnorm>=0.1.1", "pydub>=0.25.1"]
ann = ["hnswlib>=0.8"]
web = ["streamlit>=1.30", "streamlit-modal>=0.1.1,<0.1.3"]

[project.scripts]
rbassist = "rbassist.cli:app"
rbassist-gui = "rbassist.gui:main"

[tool.setuptools]
include-package-data = false

[tool.setuptools.packages.find]
include = ["rbassist*"]
exclude = ["tests*", "data*", "config*"]
'@
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($pj, $clean, $utf8NoBom)
Succ "Replaced pyproject.toml with clean version (no BOM)."

# Validate using tomllib.load (safe and robust)
Info "`nValidating TOML using python (tomllib.load)..."
$pyScript = @"
import tomllib, sys
try:
    with open('pyproject.toml','rb') as f:
        tomllib.load(f)
    print('TOML_VALID')
except Exception as e:
    print('TOML_ERROR:', e)
    sys.exit(2)
"@

$val = & $pythonExe -c $pyScript 2>&1
if ($LASTEXITCODE -ne 0 -or $val -notlike "*TOML_VALID*") {
    Err "TOML validation failed:"
    Write-Host $val
    Err "Restoring backup for debugging..."
    Copy-Item $bak $pj -Force
    Err "Original pyproject restored to $bak. Exiting."
    exit 1
}
Succ "pyproject.toml validated OK."

# Upgrade pip/setup tools
Info "`nUpgrading pip/setuptools/wheel..."
& $pythonExe -m pip install --upgrade pip setuptools wheel

# Build extras arg if provided
$extrasArg = ""
if ($Extras.Trim() -ne "") {
    $parts = $Extras.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    if ($parts.Count -gt 0) { $extrasArg = ".[" + ($parts -join ",") + "]" }
}

# Install editable package
Info "`nInstalling rbassist (editable) with extras $extrasArg ..."
$pipArgs = @("-m", "pip", "install", "-e", ".${extrasArg}")
$proc = Start-Process -FilePath $pythonExe -ArgumentList $pipArgs -NoNewWindow -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    Err "pip install failed (exit $($proc.ExitCode)). See pip output above for specific package errors."
    Err "Common next steps: if hnswlib fails, install MSVC Build Tools; if torch fails, install a matching wheel for your CUDA."
    exit 1
}
Succ "pip install -e . completed."

if ($RunStreamlit) {
    Info "`nLaunching Streamlit (rbassist/webapp.py)..."
    Start-Process -FilePath $pythonExe -ArgumentList "-m","streamlit","run","rbassist/webapp.py"
    Succ "Streamlit started in separate process."
}

Succ "`nAll done."
