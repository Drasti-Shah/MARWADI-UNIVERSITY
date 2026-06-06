# Marwadi University Admission Voice Agent - dev runner (Windows PowerShell)
# Usage:  .\run.ps1

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Activating venv + installing requirements..." -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host "WARNING: .env not found. Copy .env.example to .env and fill it in." -ForegroundColor Yellow
}

$port = 8000
if ($env:PORT) { $port = $env:PORT }

Write-Host "Starting FastAPI on http://localhost:$port ..." -ForegroundColor Green
Write-Host "In a SECOND terminal run:  ngrok http $port" -ForegroundColor Green
uvicorn app.main:app --host 0.0.0.0 --port $port --reload
