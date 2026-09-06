# ---------------------------------------------------------------------------
# Demarre l'API DCUHAT (Django) sur le poste de developpement.
#
#   .\demarrer-api.ps1
#
# Le script active l'environnement virtuel et retrouve seul les bibliotheques
# geospatiales fournies par le bundle PostGIS, dont le nom de fichier change
# a chaque version de GDAL.
# ---------------------------------------------------------------------------

$racine = Split-Path -Parent $MyInvocation.MyCommand.Definition
$backend = Join-Path $racine "backend"
Set-Location $backend

$pgBin = "C:\Program Files\PostgreSQL\16\bin"

if (-not $env:GDAL_LIBRARY_PATH) {
    $gdal = Get-ChildItem $pgBin -Filter "libgdal-*.dll" -ErrorAction SilentlyContinue |
            Select-Object -First 1
    if ($gdal) {
        $env:GDAL_LIBRARY_PATH = $gdal.FullName
    } else {
        Write-Warning "GDAL introuvable dans $pgBin — les fonctions geospatiales echoueront."
    }
}
if (-not $env:GEOS_LIBRARY_PATH) {
    $env:GEOS_LIBRARY_PATH = Join-Path $pgBin "libgeos_c.dll"
}

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Error "Environnement virtuel absent. Creez-le : python -m venv .venv"
    exit 1
}

& .\.venv\Scripts\Activate.ps1

Write-Host ""
Write-Host "  API DCUHAT       http://127.0.0.1:8000/" -ForegroundColor Green
Write-Host "  Administration   http://127.0.0.1:8000/admin/" -ForegroundColor DarkGray
Write-Host "  Documentation    http://127.0.0.1:8000/api/docs/" -ForegroundColor DarkGray
Write-Host "  Arreter          Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

python manage.py runserver
