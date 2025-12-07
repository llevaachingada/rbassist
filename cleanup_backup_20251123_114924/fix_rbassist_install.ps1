<#
Fixer script for rbassist:
- backups pyproject.toml
- writes a clean pyproject.toml (safe minimal + optional-deps)
- validates TOML
- creates venv optionally
- upgrades pip/setuptools/wheel in the chosen python
- installs package editable (pip install -e .)
- optional extras and optional Streamlit start

Usage examples:
  .\fix_rbassist_install.ps1
  .\fix_rbassist_install.ps1 -Extras "ml,stems" -RunStreamlit
  .\fix_rbassist_install.ps1 -CreateVenv -Extras "audio"
#>

param(
    [switch]$CreateVenv = $false,
    [string]$Extras = "",
    [switch]$RunStreamlit = $false
)

function Write-Info($s){ Write-Host $s -ForegroundColor Cyan }
function Write-Err($s){ Write-Host $s -ForegroundColor Red }
function Write-Succ($s){ Write-Host $s -ForegroundColor Green }

# Ensure script executed from repo root (where pyproject.toml lives)
$repoRoot = Get-Location
Write-Info "Repo root: $repoRoot"

# If user requested venv creation, do it now
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if ($CreateVenv) {
    if (-not (Test-Path $venvPython)) {
        Write-Info "Creating virtualenv at $venvPath..."
        python -m venv $venvPath
        if (-not (Test-Path $venvPython)) {
            Write-Err "Failed to create virtualenv. Make sure 'python' is on PATH."
            exit 1
        }
        Write-Succ "Virtualenv created."
    } else {
        Write-Info "Virtualenv already exists at $venvPath"
    }
}

# Prefer venv python if available
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { (Get-Command python -ErrorAction SilentlyContinue).Source }

if (-not $pythonExe) {
    Write-Err "No python executable found. Install Python 3.10+ and re-run, or create a virtualenv with -CreateVenv."
    exit 1
}

Write-Info "Using Python: $pythonExe"

# Backup pyproject.toml
$pj = Join-Path $repoRoot "pyproject.toml"
if (-not (Test-Path $pj)) {
    Write-Err "pyproject.toml not found in $repoRoot. Aborting."
    exit 1
}
$bak = "$pj.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $pj $bak -Force
Write-Succ "Backed up pyproject.toml → $bak"

# Show first 20 lines (helpful for debugging)
Write-Info "`n--- head of current pyproject.toml (first 20 lines) ---"
Get-Content $pj -TotalCount 20 | ForEach-Object { "{0}: {1}" -f ($global:i = ($global:i + 1) -as [int]) , $_ }
Remove-Variable i -ErrorAction SilentlyContinue

# Replace with a clean pyproject.toml (no BOM)
Write-Info "`nWriting clean pyproject.toml..."
$toml = @'
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

# Write without BOM for compatibility with tomllib
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($pj, $toml, $utf8NoBom)
Write-Succ "pyproject.toml replaced (clean, no BOM)."

# Validate TOML using python's tomllib
Write-Info "`nValidating pyproject.toml with tomllib..."
$validateCmd = @"
import tomllib, sys
s = open('pyproject.toml','rb').read()
try:
    tomllib.loads(s)
    print('TOML-OK')
except Exception as e:
    print('TOML-ERR:', e)
    sys.exit(2)
"@
$valOutput = & $pythonExe -c $validateCmd 2>&1
if ($LASTEXITCODE -ne 0 -or $valOutput -notlike "*TOML-OK*") {
    Write-Err "TOML validation failed:`n$valOutput"
    Write-Err "Restoring backup..."
    Copy-Item $bak $pj -Force
    Write-Err "Restored original pyproject.toml to help debug. Exiting."
    exit 1
} else {
    Write-Succ "pyproject.toml validated OK."
}

# upgrade pip/setuptools/wheel
Write-Info "`nUpgrading pip/setuptools/wheel in $pythonExe..."
& $pythonExe -m pip install --upgrade pip setuptools wheel | ForEach-Object { $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to upgrade pip/setuptools/wheel; continuing might fail."
}

# Construct extras arg if requested
$extrasArg = ""
if ($Extras -and $Extras.Trim().Length -gt 0) {
    # sanitize and build like .[a,b]
    $parts = $Extras.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    if ($parts.Count -gt 0) {
        $extrasArg = ".[" + ($parts -join ",") + "]"
    }
}

# Install editable package
Write-Info "`nInstalling rbassist (editable) ..."
$installCmd = "-m", "pip", "install", "-e", ".${extrasArg}"
Write-Info "Running: $pythonExe $($installCmd -join ' ')"
$proc = Start-Process -FilePath $pythonExe -ArgumentList $installCmd -NoNewWindow -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    Write-Err "pip install -e . failed with exit code $($proc.ExitCode). Check the pip output above for the failing package."
    Write-Err "Common culprits: building hnswlib (needs MSVC Build Tools) or torch/transformers (need specific wheels)."
    exit 1
}
Write-Succ "Package installed editable with extras $extrasArg"

# Optionally run Streamlit
if ($RunStreamlit) {
    Write-Info "`nLaunching Streamlit app (rbassist/webapp.py) using same Python..."
    # Use Start-Process so the script ends but Streamlit keeps running in separate window
    Start-Process -FilePath $pythonExe -ArgumentList "-m","streamlit","run","rbassist/webapp.py" -NoNewWindow
    Write-Succ "Streamlit launched. Open the URL printed by Streamlit in your browser."
}

Write-Succ "`nAll done. If you get any further errors from pip about building wheels, paste them into the chat and I will help triage the specific package (e.g., hnswlib -> install MSVC Build Tools, torch -> choose correct CUDA wheel)."
