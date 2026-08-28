$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[1/4] Creating Python virtual environment..."
    python -m venv .venv
}

Write-Host "[2/4] Installing Python dependencies..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host "[3/4] Installing Playwright Chromium..."
& $venvPython -m playwright install chromium

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "[4/4] Created .env from .env.example."
} else {
    Write-Host "[4/4] Existing .env preserved."
}

Write-Host ""
Write-Host "Setup complete. Edit .env, then run .\run.ps1"
