Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$backendPython = Join-Path $backendDir ".venv\Scripts\python.exe"
$frontendNodeModules = Join-Path $frontendDir "node_modules"

if (-not (Test-Path $backendPython)) {
    throw "backend/.venv was not found. Create it first and install backend requirements."
}

if (-not (Test-Path $frontendNodeModules)) {
    npm --prefix $frontendDir ci
}

function Test-PortFree {
    param([int]$Port)
    return -not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Get-FreePort {
    param([int]$PreferredPort)
    for ($port = $PreferredPort; $port -lt ($PreferredPort + 50); $port++) {
        if (Test-PortFree -Port $port) {
            return $port
        }
    }
    throw "No free port was found from $PreferredPort."
}

function Wait-Port {
    param(
        [int]$Port,
        [string]$Name,
        [int]$TimeoutSeconds = 90
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    throw "$Name did not start within $TimeoutSeconds seconds."
}

$backendPort = Get-FreePort -PreferredPort 17651
$frontendPort = Get-FreePort -PreferredPort 5173
$runLogRoot = Join-Path $env:TEMP "sjhl-sp-manager-run"
New-Item -ItemType Directory -Force -Path $runLogRoot | Out-Null
$backendOut = Join-Path $runLogRoot "backend.out.log"
$backendErr = Join-Path $runLogRoot "backend.err.log"
$frontendOut = Join-Path $runLogRoot "frontend.out.log"
$frontendErr = Join-Path $runLogRoot "frontend.err.log"
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction Stop
}
$npmCmd = $npmCommand.Source

$oldEnv = @{
    SJHL_PORT = $env:SJHL_PORT
    SJHL_CORS_ORIGINS = $env:SJHL_CORS_ORIGINS
    SJHL_BACKEND_URL = $env:SJHL_BACKEND_URL
}

try {
    $env:SJHL_PORT = "$backendPort"
    $env:SJHL_CORS_ORIGINS = "http://127.0.0.1:$frontendPort,http://localhost:$frontendPort"
    $env:SJHL_BACKEND_URL = "http://127.0.0.1:$backendPort"

    $backendProcess = Start-Process `
        -FilePath $backendPython `
        -ArgumentList "run.py" `
        -WorkingDirectory $backendDir `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr

    $frontendProcess = Start-Process `
        -FilePath $npmCmd `
        -ArgumentList "exec", "vite", "--", "--host", "0.0.0.0", "--port", "$frontendPort", "--strictPort" `
        -WorkingDirectory $frontendDir `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr

    Wait-Port -Port $backendPort -Name "backend"
    Wait-Port -Port $frontendPort -Name "frontend"

    Write-Host "Backend:  http://127.0.0.1:$backendPort"
    Write-Host "Frontend: http://127.0.0.1:$frontendPort"
    Write-Host "Logs:     $runLogRoot"
    Start-Process "http://127.0.0.1:$frontendPort" | Out-Null
}
catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Logs: $runLogRoot" -ForegroundColor Yellow
    throw
}
finally {
    $env:SJHL_PORT = $oldEnv.SJHL_PORT
    $env:SJHL_CORS_ORIGINS = $oldEnv.SJHL_CORS_ORIGINS
    $env:SJHL_BACKEND_URL = $oldEnv.SJHL_BACKEND_URL
}
