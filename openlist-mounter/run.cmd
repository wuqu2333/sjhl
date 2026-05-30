@echo off
cd /d "%~dp0"

REM 检查 Python 是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

REM 安装依赖 (静默)
python -m pip install -q fastapi uvicorn httpx >nul 2>&1

echo.
echo === SP to OpenList 自动挂载管理器 ===
echo 地址: http://127.0.0.1:17653
echo.

echo 文件修改后自动重启已开启
echo.
start http://127.0.0.1:17653
python -m uvicorn server:app --host 0.0.0.0 --port 17653 --reload --reload-dir .
pause
