$ErrorActionPreference = "Stop"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher not found. Install Python 3.12 or newer first."
}

py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example. Add one provider key when ready."
}

Write-Host "Setup complete. Run: .\.venv\Scripts\python.exe run.py"
