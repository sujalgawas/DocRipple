<#
.SYNOPSIS
    Starts DocRipple Backend (Agent + FastAPI at http://localhost:8000) and Frontend (Vite at http://localhost:5173).
.DESCRIPTION
    Executes the unified runner python run.py, or launches services directly if Python is not in PATH.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$ScriptDir\run.py"
    exit $LASTEXITCODE
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py "$ScriptDir\run.py"
    exit $LASTEXITCODE
} else {
    Write-Host "[DocRipple] Python not found in PATH. Launching services in dedicated windows..." -ForegroundColor Yellow

    $backendDir = Join-Path $ScriptDir "docsync-agent"
    $frontendDir = Join-Path $ScriptDir "frontend"

    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendDir'; if (Test-Path '.venv\Scripts\activate.ps1') { . .venv\Scripts\activate.ps1 }; uvicorn src.main:app --reload --port 8000"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendDir'; npm run dev"

    Write-Host "[DocRipple] Backend:  http://localhost:8000" -ForegroundColor Cyan
    Write-Host "[DocRipple] Frontend: http://localhost:5173" -ForegroundColor Magenta
}
