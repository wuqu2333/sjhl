from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "SJHL-SP-Manager"
APPDATA = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
DATA_DIR = Path(os.environ.get("SJHL_DATA_DIR", str(Path(APPDATA) / APP_NAME)))
HOST = os.environ.get("SJHL_HOST", "127.0.0.1")
PORT = int(os.environ.get("SJHL_PORT", "17651"))
TRANSFER_CONCURRENCY = max(1, int(os.environ.get("SJHL_TRANSFER_CONCURRENCY", "4")))


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
GRAPH_BASE_URL = os.environ.get(
    "SJHL_GRAPH_BASE_URL", "https://microsoftgraph.chinacloudapi.cn/v1.0"
)
AUTH_BASE_URL = os.environ.get(
    "SJHL_AUTH_BASE_URL", "https://login.partner.microsoftonline.cn"
)


GRAPH_REGIONS = {
    "cn": {
        "label": "世纪互联",
        "graphBaseUrl": "https://microsoftgraph.chinacloudapi.cn/v1.0",
        "authBaseUrl": "https://login.partner.microsoftonline.cn",
    },
    "global": {
        "label": "全球",
        "graphBaseUrl": "https://graph.microsoft.com/v1.0",
        "authBaseUrl": "https://login.microsoftonline.com",
    },
    "us": {
        "label": "美国政府",
        "graphBaseUrl": "https://graph.microsoft.us/v1.0",
        "authBaseUrl": "https://login.microsoftonline.us",
    },
    "de": {
        "label": "德国",
        "graphBaseUrl": "https://graph.microsoft.de/v1.0",
        "authBaseUrl": "https://login.microsoftonline.de",
    },
}


def resolve_graph_region(region: str = "cn") -> dict[str, str]:
    return GRAPH_REGIONS.get(region or "cn", GRAPH_REGIONS["cn"])
