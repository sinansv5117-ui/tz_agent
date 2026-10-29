# Travelzync quick-start script for PowerShell

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example."
    Write-Host "Add your GROQ_API_KEY and verify DATABASE_URL before continuing."
    exit
}

python -m app.db.init_db
python -m app.main
