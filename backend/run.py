from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

import uvicorn

from app.main import app
from config.settings import HOST, PORT


def open_browser_for_frozen_app() -> None:
    if not getattr(sys, "frozen", False):
        return
    if os.environ.get("SJHL_OPEN_BROWSER", "1") == "0":
        return

    def open_later() -> None:
        time.sleep(1.5)
        browser_host = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
        webbrowser.open(f"http://{browser_host}:{PORT}")

    threading.Thread(target=open_later, daemon=True).start()


def main() -> None:
    open_browser_for_frozen_app()
    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="info")
    except Exception:
        import traceback as _tb
        crash_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
        with open(crash_log, "w", encoding="utf-8") as f:
            f.write(_tb.format_exc())
        raise


if __name__ == "__main__":
    main()
