# Arranque local — usa TIDB_* del .env (no DATABASE_URL de Vercel en la shell)
Set-Location (Split-Path $PSScriptRoot -Parent)
foreach ($v in @('DATABASE_URL', 'VERCEL', 'VERCEL_ENV', 'VERCEL_DEPLOYMENT_ID', 'VERCEL_URL')) {
    Remove-Item "Env:$v" -ErrorAction SilentlyContinue
}
$env:FLASK_PORT = "5001"
$env:APP_URL = "http://localhost:5001"
Write-Host "Verificando TiDB (desde .env)..." -ForegroundColor Cyan
python -m scripts.verificar_tidb
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "AVISO: TiDB no alcanzable. La app arranca igual (memoria); revise red o TiDB Cloud." -ForegroundColor Yellow
    Write-Host ""
}
python -m src.app.main
