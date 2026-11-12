param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install requirements.txt first; see README.md.'
}

Push-Location (Join-Path $projectRoot 'web')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Front-end dependency installation failed.' }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Front-end build failed.' }
} finally {
    Pop-Location
}

Write-Host "Ball Knowledge: http://localhost:$Port"
& $pythonPath -m uvicorn edgefinder.api.app:app --app-dir (Join-Path $projectRoot 'src') --port $Port
