Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $root
try {
    if (-not (Test-Path .\frontend\node_modules)) {
        npm --prefix frontend ci
    }

    npm --prefix frontend run build

    & .\backend\.venv\Scripts\python.exe -m pip install pyinstaller

    & .\backend\.venv\Scripts\pyinstaller.exe `
        --noconfirm `
        --clean `
        --onefile `
        --name SJHL-SP-Manager `
        --distpath .\backend\release `
        --workpath .\backend\build `
        --specpath .\backend `
        --add-data "..\frontend\dist;frontend\dist" `
        --collect-all p115client `
        --collect-all qrcode `
        --collect-all PIL `
        --collect-all duckdb `
        .\backend\run.py
}
finally {
    Pop-Location
}
