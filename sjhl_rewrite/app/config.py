from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("SJHL_REWRITE_DATA_DIR", str(BASE_DIR / "data")))
DOWNLOAD_DIR = Path(os.environ.get("SJHL_REWRITE_DOWNLOAD_DIR", str(DATA_DIR / "downloads")))
HOST = os.environ.get("SJHL_REWRITE_HOST", "127.0.0.1")
PORT = int(os.environ.get("SJHL_REWRITE_PORT", "17652"))

GRAPH_BASE_URL = os.environ.get("SJHL_GRAPH_BASE_URL", "https://microsoftgraph.chinacloudapi.cn/v1.0")
AUTH_BASE_URL = os.environ.get("SJHL_AUTH_BASE_URL", "https://login.partner.microsoftonline.cn")

GRAPH_CHUNK_UNIT = 320 * 1024
GRAPH_MAX_CHUNK_SIZE = 191 * GRAPH_CHUNK_UNIT
SMALL_UPLOAD_CHUNK_SIZE = 20 * 1024 * 1024
MID_UPLOAD_CHUNK_SIZE = 40 * 1024 * 1024
LARGE_UPLOAD_CHUNK_SIZE = 60 * 1024 * 1024

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
CLOUDDRIVE_CLIENT_ID = 100195313
CLOUDDRIVE_REDIRECT_URI = "https://redirect115.zhenyunpan.com"
CLOUDDRIVE_AUTHORIZE_URL = "https://passportapi.115.com/open/authorize"


def normalize_chunk_size(value: int) -> int:
    size = int(value or 0)
    if size <= 0:
        return 0
    size -= size % GRAPH_CHUNK_UNIT
    return min(GRAPH_MAX_CHUNK_SIZE, max(GRAPH_CHUNK_UNIT, size))


def auto_chunk_size(total_size: int) -> int:
    size = int(total_size or 0)
    if size and size <= 1024 * 1024 * 1024:
        return SMALL_UPLOAD_CHUNK_SIZE
    if size and size >= 20 * 1024 * 1024 * 1024:
        return LARGE_UPLOAD_CHUNK_SIZE
    return MID_UPLOAD_CHUNK_SIZE

