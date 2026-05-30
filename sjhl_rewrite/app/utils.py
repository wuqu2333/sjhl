from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_remote_dir(value: Any) -> str:
    raw = clean(value).replace("\\", "/").strip("/")
    return "/".join(part.strip() for part in raw.split("/") if part.strip())


def join_remote_path(*parts: Any) -> str:
    clean_parts: list[str] = []
    for part in parts:
        raw = clean(part).replace("\\", "/").strip("/")
        if raw:
            clean_parts.extend(segment for segment in raw.split("/") if segment)
    if not clean_parts:
        return ""
    return "/".join(clean_parts)


def encode_graph_drive_path(remote_path: str) -> str:
    return "/".join(quote(part, safe="") for part in remote_path.replace("\\", "/").split("/") if part)


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def json_loads(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def format_bytes(size: int) -> str:
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} PB"


def ensure_parent(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def monotonic() -> float:
    return time.monotonic()
