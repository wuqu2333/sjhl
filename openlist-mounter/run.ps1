# SP → OpenList 自动挂载管理器 - 启动脚本
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 检查 Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.9+" -ForegroundColor Red
    pause
    exit 1
}

# 安装依赖 (静默)
python -m pip install -q fastapi uvicorn httpx 2>&1 | Out-Null

Write-Host ""
Write-Host "=== SP → OpenList 自动挂载管理器 ===" -ForegroundColor Cyan
Write-Host "地址: http://127.0.0.1:17653" -ForegroundColor Green
Write-Host ""

Write-Host "文件修改后自动重启已开启" -ForegroundColor Yellow
Write-Host ""

Start-Process "http://127.0.0.1:17653"
python -m uvicorn server:app --host 0.0.0.0 --port 17653 --reload --reload-dir .
pause
