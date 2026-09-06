# ---------------------------------------------------------------------------
# Demarre l'interface web DCUHAT (Vite) sur le poste de developpement.
#
#   .\demarrer-interface.ps1
#
# A lancer dans un second terminal, l'API devant tourner en parallele.
# ---------------------------------------------------------------------------

$racine = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location (Join-Path $racine "frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "Premiere execution : installation des dependances..." -ForegroundColor Yellow
    npm install
}

Write-Host ""
Write-Host "  Interface DCUHAT   http://localhost:5173" -ForegroundColor Green
Write-Host "  Arreter            Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

npm run dev
