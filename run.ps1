param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $AgentArgs
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment not found. Run .\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath ".env")) {
    throw ".env not found. Run .\setup.ps1, then enter your API and target URL."
}

$configuration = Get-Content -LiteralPath ".env" -Raw
if (
    $configuration -match "TARGET_URL=https://example\.com/quiz" -or
    $configuration -match "LLM_API_KEY=your-api-key" -or
    $configuration -match "LLM_MODEL=your-model-name"
) {
    throw "Edit .env and replace the example target URL, API key, and model name first."
}

& $venvPython main.py @AgentArgs
exit $LASTEXITCODE
