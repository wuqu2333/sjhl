$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

if (!(Test-Path $Python)) {
  py -3 -m venv $Venv
}

& $Python -m pip install -U pip
& $Python -m pip install -r (Join-Path $Root "requirements.txt")

$env:PYTHONPATH = $Root
$HostAddr = if ($env:SJHL_REWRITE_HOST) { $env:SJHL_REWRITE_HOST } else { "127.0.0.1" }
$Port = if ($env:SJHL_REWRITE_PORT) { $env:SJHL_REWRITE_PORT } else { "17652" }

Start-Process "http://$HostAddr`:$Port"
& $Python -m uvicorn app.main:app --host $HostAddr --port $Port

