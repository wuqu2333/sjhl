"""后端自动重启守护进程。后端崩溃时自动拉起。"""
from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path

VENV_PYTHON = str(Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe")
BACKEND_SCRIPT = str(Path(__file__).resolve().parent / "run.py")
MAX_RESTARTS = 50
RESTART_DELAY = 5

def main():
    restarts = 0
    while restarts < MAX_RESTARTS:
        restarts += 1
        print(f"[watchdog] 启动后端 (第 {restarts} 次)")
        proc = subprocess.Popen(
            [VENV_PYTHON, BACKEND_SCRIPT],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        proc.wait()
        print(f"[watchdog] 后端退出 (exit={proc.returncode})，{RESTART_DELAY}s 后重启...")
        time.sleep(RESTART_DELAY)
    print("[watchdog] 达到最大重启次数，退出")

if __name__ == "__main__":
    main()
