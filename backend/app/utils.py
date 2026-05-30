from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


def clean(value: object) -> str:
    return str(value or "").strip()


def normalize_remote_dir(value: object) -> str:
    raw = clean(value).replace("\\", "/").strip("/")
    return "/".join(part.strip() for part in raw.split("/") if part.strip())


def join_remote_path(remote_dir: object, file_name: object) -> str:
    clean_dir = normalize_remote_dir(remote_dir)
    name = clean(file_name).replace("\\", "/").split("/")[-1]
    if not name:
        raise ValueError("文件名不能为空")
    return f"{clean_dir}/{name}" if clean_dir else name


def encode_graph_drive_path(remote_path: str) -> str:
    return "/".join(quote(part, safe="") for part in remote_path.replace("\\", "/").split("/") if part)


def safe_file_name_from_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    name = unquote(parsed.path.split("/")[-1])
    return name or "115-source"


def hash_file(file_path: str | Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with Path(file_path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_local_files(local_path: str | Path, recursive: bool = False) -> tuple[Path, list[Path]]:
    path = Path(local_path).resolve()
    if path.is_file():
        return path.parent, [path]
    if not path.is_dir():
        raise ValueError("本地路径必须是文件或文件夹")
    pattern = "**/*" if recursive else "*"
    return path, [item for item in path.glob(pattern) if item.is_file()]


def relative_remote_dir(base_remote_dir: str, base_local_path: Path, file_path: Path) -> str:
    relative_parent = file_path.parent.relative_to(base_local_path).as_posix()
    if relative_parent == ".":
        relative_parent = ""
    return normalize_remote_dir("/".join(part for part in [base_remote_dir, relative_parent] if part))
