from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Query

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.settings import AppSettingsRequest


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(container: AppContainer = Depends(get_container)):
    return {"ok": True, "settings": container.app_settings.get()}


@router.post("")
def save_settings(body: AppSettingsRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "settings": container.app_settings.update(body.model_dump(exclude_none=True))}
    except Exception as error:
        raise_bad_request(error)


def _free_gb(p: Path) -> float:
    try:
        return shutil.disk_usage(p).free / (1024 ** 3)
    except Exception:
        return -1


@router.get("/browse-dir")
def browse_dir(path: str = Query(default="")):
    try:
        base = Path(path) if path else None

        # 空路径 -> 显示驱动器列表
        if base is None or str(base) == ".":
            drives = []
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                dp = Path(f"{letter}:\\")
                if dp.exists():
                    fg = _free_gb(dp)
                    label = f"{letter}:盘" if fg < 0 else f"{letter}:盘 ({fg:.0f} GB 可用)"
                    drives.append({"name": label, "path": str(dp)})
            return {"ok": True, "path": "此电脑", "parent": None, "dirs": drives, "freeGb": -1}

        if not base.exists():
            base = Path.home()

        is_root = base.parent == base
        parent = "" if is_root else str(base.parent)
        dirs = []
        for item in sorted(base.iterdir()):
            if item.is_dir() and not item.name.startswith('.'):
                dirs.append({"name": item.name, "path": str(item)})
        fg = _free_gb(base)
        return {"ok": True, "path": str(base), "parent": parent, "dirs": dirs, "freeGb": round(fg, 1)}
    except PermissionError:
        fg = _free_gb(base) if base and base.exists() else -1
        p = str(base) if base else ""
        pp = "" if (base and base.parent == base) else (str(base.parent) if base else "")
        return {"ok": True, "path": p, "parent": pp, "dirs": [], "freeGb": round(fg, 1), "error": "权限不足"}
    except Exception as e:
        raise_bad_request(e)


@router.post("/browse-dir/mkdir")
def mkdir_in_dir(path: str = Query(default=""), name: str = Body(default="", embed=True)):
    if not name or not name.strip():
        raise_bad_request("文件夹名称不能为空")
    try:
        target = Path(path) / name.strip()
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": str(target)}
    except Exception as e:
        raise_bad_request(e)
