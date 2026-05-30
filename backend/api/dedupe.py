from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request


router = APIRouter(prefix="/dedupe", tags=["dedupe"])


@router.get("")
def list_dedupe(container: AppContainer = Depends(get_container)):
    return {"ok": True, "items": container.dedupe.list(5000)}


@router.delete("")
def clear_dedupe(container: AppContainer = Depends(get_container)):
    container.dedupe.clear()
    return {"ok": True}


@router.get("/duplicates")
def find_duplicates(container: AppContainer = Depends(get_container)):
    """查找重复文件：同一 hash 出现在多个 SP 或路径下的文件"""
    dups = container.dedupe.find_duplicates()
    return {"ok": True, "groups": dups}


class DeleteFileRequest(BaseModel):
    profile_id: str
    item_id: str


@router.post("/delete-file")
async def delete_file(body: DeleteFileRequest, container: AppContainer = Depends(get_container)):
    """删除 SP 上的一个文件并清理去重索引"""
    try:
        profile = container.profiles.get(body.profile_id)
        if not profile:
            raise ValueError("SP 配置不存在")
        await container.graph.request(profile, "DELETE", f"/drives/{profile['driveId']}/items/{body.item_id}")
        container.dedupe.remove_by_item(body.item_id)
        return {"ok": True}
    except Exception as error:
        raise_bad_request(error)
