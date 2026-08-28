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

$chromeCandidates = @(
    [Environment]::ExpandEnvironmentVariables("%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    [Environment]::ExpandEnvironmentVariables("%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    [Environment]::ExpandEnvironmentVariables("%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
)
$chromeInstalled = $chromeCandidates | Where-Object {
    $_ -and (Test-Path -LiteralPath $_)
} | Select-Object -First 1

if ($chromeInstalled) {
    Write-Host "[3/4] System Chrome found; bundled Chromium is not required."
} else {
    Write-Host "[3/4] Chrome not found; installing Playwright Chromium..."
    & $venvPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        throw "Chromium installation failed. Install Google Chrome manually or retry setup.ps1."
    }
}

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "[4/4] Created .env from .env.example."
} else {
    Write-Host "[4/4] Existing .env preserved."
}

Write-Host ""
Write-Host "Setup complete. Edit .env, then run .\run.ps1"
