from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import DATA_DIR
from .db import Database, Store
from .graph import GraphClient
from .pan115 import Pan115Client
from .transfer import TransferManager


db = Database(DATA_DIR)
store = Store(db)
graph = GraphClient()
pan115 = Pan115Client()
transfer = TransferManager(store, graph, pan115)

app = FastAPI(title="SJHL Rewrite", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def fail(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@app.get("/api/state")
async def state() -> dict[str, Any]:
    return {
        "stats": store.stats(),
        "settings": store.get_settings(),
        "profiles": store.list_profiles(),
        "accounts": store.list_accounts(),
        "jobs": store.list_jobs(200),
        "workerRunning": transfer.running,
    }


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    return store.get_settings()


@app.post("/api/settings")
async def set_settings(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return store.set_settings(payload)


@app.get("/api/profiles")
async def list_profiles() -> list[dict[str, Any]]:
    return store.list_profiles()


@app.post("/api/profiles")
async def save_profile(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        profile = store.upsert_profile(payload)
        profile["client_secret"] = "***" if profile.get("client_secret") else ""
        return profile
    except Exception as exc:
        raise fail(exc)


@app.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> dict[str, bool]:
    store.delete_profile(profile_id)
    return {"ok": True}


@app.post("/api/profiles/{profile_id}/test")
async def test_profile(profile_id: str) -> dict[str, Any]:
    profile = store.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="SP 配置不存在")
    try:
        token = await graph.token(profile)
        return {"ok": True, "tokenPrefix": token[:12]}
    except Exception as exc:
        raise fail(exc)


@app.get("/api/115/accounts")
async def list_accounts() -> list[dict[str, Any]]:
    return store.list_accounts()


@app.post("/api/115/accounts")
async def save_account(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        account = store.upsert_account(payload)
        for key in ("cookie", "access_token", "refresh_token"):
            if account.get(key):
                account[key] = "***"
        return account
    except Exception as exc:
        raise fail(exc)


@app.delete("/api/115/accounts/{account_id}")
async def delete_account(account_id: str) -> dict[str, bool]:
    store.delete_account(account_id)
    return {"ok": True}


@app.post("/api/115/accounts/{account_id}/clouddrive-token")
async def clouddrive_token(account_id: str) -> dict[str, Any]:
    account = store.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="115 账号不存在")
    try:
        tokens = await pan115.clouddrive_get_tokens_by_cookie(account.get("cookie") or "")
        store.update_account_tokens(account_id, tokens["accessToken"], tokens.get("refreshToken") or "")
        return {"ok": True, "hasAccessToken": True, "hasRefreshToken": bool(tokens.get("refreshToken"))}
    except Exception as exc:
        raise fail(exc)


@app.post("/api/115/downurl")
async def test_downurl(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    account = store.get_account(payload.get("accountId") or payload.get("account_id") or "")
    if not account:
        raise HTTPException(status_code=404, detail="115 账号不存在")
    try:
        result = await pan115.down_url_auto(account, payload.get("pickCode") or payload.get("pick_code") or "")
        if result.get("accessToken") and result.get("refreshToken"):
            store.update_account_tokens(account["id"], result["accessToken"], result["refreshToken"])
        result["url"] = result.get("url", "")[:80] + "..." if result.get("url") else ""
        return result
    except Exception as exc:
        raise fail(exc)


@app.get("/api/jobs")
async def list_jobs(limit: int = 200) -> list[dict[str, Any]]:
    return store.list_jobs(limit)


@app.post("/api/jobs/115")
async def create_115_job(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return transfer.create_115_job(payload)
    except Exception as exc:
        raise fail(exc)


@app.post("/api/jobs/local")
async def create_local_job(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return transfer.create_local_job(payload)
    except Exception as exc:
        raise fail(exc)


@app.post("/api/jobs/process")
async def process_jobs() -> dict[str, Any]:
    transfer.start()
    return {"ok": True, "workerRunning": transfer.running}


@app.post("/api/jobs/stop")
async def stop_jobs() -> dict[str, Any]:
    await transfer.stop()
    return {"ok": True, "workerRunning": transfer.running}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str) -> dict[str, Any]:
    job = store.retry_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str) -> dict[str, bool]:
    store.delete_job(job_id)
    return {"ok": True}


@app.delete("/api/jobs")
async def clear_done() -> dict[str, bool]:
    db.execute("DELETE FROM transfer_jobs WHERE status IN ('done', 'failed')")
    return {"ok": True}


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await transfer.stop()
    db.close()


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

