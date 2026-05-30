from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.worker import WorkerFailedRequest, WorkerProgressRequest

router = APIRouter(prefix="/worker", tags=["worker"])


@router.get("/tasks")
def list_worker_tasks(container: AppContainer = Depends(get_container)):
    limit = 50
    tasks = container.jobs.list_worker_available(limit)
    return {"ok": True, "tasks": tasks, "total": len(tasks)}


@router.post("/tasks/{job_id}/claim")
def claim_task(job_id: str, container: AppContainer = Depends(get_container)):
    try:
        task = container.jobs.claim_for_worker(job_id)
        return {"ok": True, "task": task}
    except ValueError as e:
        raise_bad_request(e)


@router.post("/tasks/{job_id}/download-url")
async def get_download_url(job_id: str, container: AppContainer = Depends(get_container)):
    try:
        download = await container.jobs.resolve_download_for_worker(job_id)
        return {"ok": True, "download": download}
    except ValueError as e:
        raise_bad_request(e)


@router.post("/tasks/{job_id}/progress")
def update_progress(job_id: str, body: WorkerProgressRequest, container: AppContainer = Depends(get_container)):
    data = body.model_dump(exclude_none=True)
    container.transfer_jobs.patch_progress(
        job_id,
        uploaded=int(data.get("uploaded") or 0),
        total=int(data.get("total") or 1),
        downloaded=int(data.get("downloaded") or 0),
    )
    if data.get("speed"):
        container.transfer_jobs.patch(job_id, {"download_speed": int(data["speed"])})
    return {"ok": True}


@router.post("/tasks/{job_id}/upload-session")
async def create_upload_session(job_id: str, container: AppContainer = Depends(get_container)):
    try:
        session = await container.jobs.create_upload_session_for_worker(job_id)
        return {"ok": True, "session": session}
    except ValueError as e:
        raise_bad_request(e)


@router.post("/tasks/{job_id}/complete")
async def complete_task(job_id: str, container: AppContainer = Depends(get_container)):
    try:
        result = await container.jobs.complete_for_worker(job_id)
        return result
    except ValueError as e:
        raise_bad_request(e)


@router.post("/tasks/{job_id}/failed")
def fail_task(job_id: str, body: WorkerFailedRequest, container: AppContainer = Depends(get_container)):
    try:
        result = container.jobs.fail_for_worker(job_id, body.error or "Worker 上报错误")
        return result
    except ValueError as e:
        raise_bad_request(e)


@router.get("/state")
def worker_state(container: AppContainer = Depends(get_container)):
    counts = container.jobs.status_counts()
    return {
        "ok": True,
        "statusCounts": counts,
        "totalPending": counts.get("queued", 0) + counts.get("retry", 0),
        "totalRunning": counts.get("running", 0),
    }
