from __future__ import annotations

import os
import sys
from pathlib import Path

from .graph_regions import GRAPH_REGIONS, resolve_graph_region


APP_NAME = "SJHL-SP-Manager"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) if getattr(sys, "frozen", False) else PROJECT_ROOT
APPDATA = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
DATA_DIR = Path(os.environ.get("SJHL_DATA_DIR", str(Path(APPDATA) / APP_NAME)))
HOST = os.environ.get("SJHL_HOST", "127.0.0.1")
PORT = int(os.environ.get("SJHL_PORT", "1115"))
TRANSFER_CONCURRENCY = max(1, int(os.environ.get("SJHL_TRANSFER_CONCURRENCY", "2")))


def parse_size(value: str, default: int = 0) -> int:
    raw = str(value or "").strip().lower()
    if raw in ("", "auto", "0"):
        return default
    units = {"k": 1024, "kb": 1024, "m": 1024**2, "mb": 1024**2, "g": 1024**3, "gb": 1024**3}
    for suffix, multiplier in sorted(units.items(), key=lambda item: len(item[0]), reverse=True):
        if raw.endswith(suffix):
            return int(float(raw[: -len(suffix)].strip()) * multiplier)
    return int(float(raw))


UPLOAD_CHUNK_SIZE = parse_size(os.environ.get("SJHL_UPLOAD_CHUNK_SIZE", "auto"), 0)
GRAPH_BASE_URL = os.environ.get("SJHL_GRAPH_BASE_URL", GRAPH_REGIONS["cn"]["graphBaseUrl"])
AUTH_BASE_URL = os.environ.get("SJHL_AUTH_BASE_URL", GRAPH_REGIONS["cn"]["authBaseUrl"])
FRONTEND_DIST_DIR = Path(
    os.environ.get(
        "SJHL_FRONTEND_DIST",
        str(RUNTIME_ROOT / "frontend" / "dist"),
    )
)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "SJHL_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:1115,http://localhost:1115",
    ).split(",")
    if origin.strip()
]
ENABLE_API_DOCS = os.environ.get("SJHL_ENABLE_DOCS", "0") == "1"
