from __future__ import annotations

import asyncio
from fastapi import APIRouter, Depends, HTTPException

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.sync_jobs import SyncJobRequest


router = APIRouter(prefix="/sync-jobs", tags=["sync-jobs"])


@router.get("")
def list_sync_jobs(container: AppContainer = Depends(get_container)):
    return {"ok": True, "syncJobs": container.sync_store.list()}


@router.post("")
def save_sync_job(body: SyncJobRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "syncJob": container.sync_store.upsert(body.model_dump(exclude_none=True))}
    except Exception as error:
        raise_bad_request(error)


@router.delete("/{sync_id}")
def remove_sync_job(sync_id: str, container: AppContainer = Depends(get_container)):
    container.sync_store.remove(sync_id)
    return {"ok": True}


@router.post("/{sync_id}/run")
async def run_sync_job(sync_id: str, container: AppContainer = Depends(get_container)):
    """异步启动同步作业，立即返回"""
    try:
        job = container.sync_store.get(sync_id)
        if not job:
            raise HTTPException(status_code=404, detail="同步作业不存在")
        asyncio.create_task(container.sync_engine.run(sync_id))
        return {"ok": True, "message": "同步已启动"}
    except HTTPException:
        raise
    except Exception as error:
        raise_bad_request(error)
