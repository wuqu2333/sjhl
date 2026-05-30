from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.files import CreateFolderRequest


router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{profile_id}/children")
async def list_profile_children(
    profile_id: str,
    path: str = Query(default=""),
    container: AppContainer = Depends(get_container),
):
    try:
        profile = container.profiles.get(profile_id)
        if not profile:
            raise ValueError("SP 配置不存在")
        public_profile = next((item for item in container.profiles.list() if item.get("id") == profile_id), {})
        items = await container.graph.list_remote_children(profile, path)
        return {"ok": True, "profile": public_profile, "path": path.replace("\\", "/").strip("/"), "items": items}
    except Exception as error:
        raise_bad_request(error)


@router.delete("/{profile_id}/items/{item_id}")
async def delete_sp_item(
    profile_id: str,
    item_id: str,
    driveId: str = Query(default=""),
    path: str = Query(default=""),
    itemType: str = Query(default="file"),
    container: AppContainer = Depends(get_container),
):
    try:
        profile = container.profiles.get(profile_id)
        if not profile:
            raise ValueError("SP 配置不存在")
        await container.graph.delete_item(profile, item_id, driveId)
        removed = 0
        if itemType == "folder" and path:
            removed += container.dedupe.remove_by_profile_path(profile_id, path)
        removed += container.dedupe.remove_by_item(item_id)
        return {"ok": True, "removed": removed}
    except Exception as error:
        raise_bad_request(error)


@router.patch("/{profile_id}/items/{item_id}")
async def rename_sp_item(
    profile_id: str,
    item_id: str,
    body: dict,
    driveId: str = Query(default=""),
    container: AppContainer = Depends(get_container),
):
    try:
        profile = container.profiles.get(profile_id)
        if not profile:
            raise ValueError("SP 配置不存在")
        result = await container.graph.rename_item(profile, item_id, body.get("name", ""), driveId)
        return {"ok": True, "item": result}
    except Exception as error:
        raise_bad_request(error)


@router.get("/{profile_id}/search")
async def search_sp_items(profile_id: str, q: str = "", container: AppContainer = Depends(get_container)):
    try:
        profile = container.profiles.get(profile_id)
        if not profile:
            raise ValueError("SP 配置不存在")
        items = await container.graph.search_items(profile, q)
        return {"ok": True, "items": items}
    except Exception as error:
        raise_bad_request(error)


@router.post("/{profile_id}/folders")
async def create_folder(
    profile_id: str,
    body: CreateFolderRequest,
    container: AppContainer = Depends(get_container),
):
    try:
        profile = container.profiles.get(profile_id)
        if not profile:
            raise ValueError("SP 配置不存在")
        item = await container.graph.create_folder(
            profile,
            body.path,
            body.name,
            body.conflictBehavior or "rename",
        )
        return {"ok": True, "item": item}
    except Exception as error:
        raise_bad_request(error)


@router.post("/{profile_id}/upload")
async def upload_file_to_profile(
    profile_id: str,
    request: Request,
    path: str = Query(default=""),
    fileName: str = Query(default=""),
    size: int | None = Query(default=None),
    conflictBehavior: str = Query(default="rename"),
    container: AppContainer = Depends(get_container),
):
    try:
        profile = container.profiles.get(profile_id)
        if not profile:
            raise ValueError("SP 配置不存在")
        if not fileName:
            raise ValueError("文件名不能为空")
        total_size = int(size if size is not None else request.headers.get("content-length") or -1)
        if total_size < 0:
            raise ValueError("无法获取上传文件大小")
        result = await container.graph.upload_stream(
            profile,
            request.stream(),
            total_size,
            path,
            fileName,
            conflictBehavior or "rename",
        )
        item = result.get("item") or {}
        if result.get("sha256"):
            container.dedupe.record(
                {
                    "algorithm": "sha256",
                    "hash": result["sha256"],
                    "size": result["size"],
                    "sourceType": "browser-upload",
                    "profileId": profile_id,
                    "remotePath": result["remotePath"],
                    "fileName": fileName,
                    "itemId": item.get("id"),
                    "webUrl": item.get("webUrl"),
                }
            )
        return {"ok": True, "result": result}
    except Exception as error:
        raise_bad_request(error)
