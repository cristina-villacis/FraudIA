# Arranque local fijo en http://localhost:5001 (lee .env)
Set-Location (Split-Path $PSScriptRoot -Parent)
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:FLASK_PORT = "5001"
$env:APP_URL = "http://localhost:5001"
python -m src.app.main
