from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.transfers import LocalUploadRequest, Pan115CookieUploadRequest, Pan115OpenUploadRequest, RemoteUrlUploadRequest
from services.pan115 import DEFAULT_UA


router = APIRouter(tags=["transfers"])


@router.get("/jobs")
def list_jobs(container: AppContainer = Depends(get_container)):
    status_counts = container.jobs.status_counts()
    return {
        "ok": True,
        "jobs": container.jobs.list(),
        "statusCounts": status_counts,
        "total": sum(status_counts.values()),
    }


@router.post("/jobs/process")
async def trigger_process(container: AppContainer = Depends(get_container)):
    await container.jobs.process()
    return {"ok": True}


@router.delete("/jobs/completed")
def clear_completed_jobs(container: AppContainer = Depends(get_container)):
    return {"ok": True, "deleted": container.jobs.clear_completed()}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, container: AppContainer = Depends(get_container)):
    return {"ok": True, "deleted": container.jobs.delete(job_id)}



@router.post("/uploads/local")
async def upload_local(body: LocalUploadRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "jobs": container.jobs.enqueue_local(body.model_dump(exclude_none=True))}
    except Exception as error:
        raise_bad_request(error)


@router.post("/uploads/115-url")
async def upload_115_url(body: RemoteUrlUploadRequest, container: AppContainer = Depends(get_container)):
    try:
        data = body.model_dump(exclude_none=True)
        source_headers = {}
        for line in (data.get("headersText") or "").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                source_headers[key.strip()] = value.strip()
        return {"ok": True, "jobs": container.jobs.enqueue_remote_url({**data, "sourceHeaders": source_headers})}
    except Exception as error:
        raise_bad_request(error)


@router.post("/uploads/115-open")
async def upload_115_open(body: Pan115OpenUploadRequest, container: AppContainer = Depends(get_container)):
    try:
        data = body.model_dump(exclude_none=True)
        user_agent = data.get("userAgent") or DEFAULT_UA
        return {
            "ok": True,
            "jobs": container.jobs.enqueue_remote_url(
                {
                    **data,
                    "sourceUrl": "",
                    "sourceHeaders": {},
                    "sourceProvider": "115-open",
                    "sourcePickCode": data.get("pickCode"),
                    "sourceAccessToken": data.get("accessToken"),
                    "sourceRefreshToken": data.get("refreshToken"),
                    "sourceUserAgent": user_agent,
                    "fileName": data.get("fileName") or data.get("pickCode"),
                    "size": data.get("size") or 0,
                    "sha1": data.get("sha1") or "",
                }
            ),
        }
    except Exception as error:
        raise_bad_request(error)


@router.post("/uploads/115-cookie")
async def upload_115_cookie(body: Pan115CookieUploadRequest, container: AppContainer = Depends(get_container)):
    try:
        data = body.model_dump(exclude_none=True)
        user_agent = data.get("userAgent") or DEFAULT_UA
        down = await container.pan115.down_url_by_cookie(data.get("cookie"), data.get("pickCode"), user_agent)
        return {
            "ok": True,
            "jobs": container.jobs.enqueue_remote_url(
                {
                    **data,
                    "sourceUrl": "",
                    "sourceHeaders": {},
                    "sourceProvider": "115-cookie",
                    "sourcePickCode": data.get("pickCode"),
                    "sourceCookie": data.get("cookie"),
                    "sourceUserAgent": user_agent,
                    "fileName": data.get("fileName") or down.get("fileName"),
                    "size": data.get("size") or down.get("size"),
                    "sha1": data.get("sha1") or down.get("sha1"),
                }
            ),
        }
    except Exception as error:
        raise_bad_request(error)


@router.post("/uploads/115-folder")
async def upload_115_folder(body: Pan115CookieUploadRequest, container: AppContainer = Depends(get_container)):
    """搬运整个115文件夹到SP，保留目录结构"""
    try:
        data = body.model_dump(exclude_none=True)
        account_id = data.get("accountId") or ""
        cookie = data.get("cookie") or ""
        cid = data.get("sourceCid") or data.get("pickCode") or "0"
        user_agent = data.get("userAgent") or DEFAULT_UA
        profile_id = data.get("profileId")
        remote_dir = data.get("remoteDir") or ""
        scan_account = {}
        if account_id:
            account = container.pan115_accounts.get(account_id)
            if not account:
                raise ValueError("115 账号不存在")
            scan_account.update(account)
        if cookie:
            scan_account["cookie"] = cookie
        if not scan_account.get("accessToken") and not scan_account.get("cookie"):
            raise ValueError("115 账号未配置有效认证，请先在设置中获取 Token 或保存 Cookie")
        if cid == "0":
            raise ValueError("请指定要搬运的文件夹 CID")
        profile = container.profiles.get(profile_id) if profile_id and profile_id not in ("__auto_capacity_pool__", "auto") else None
        if not profile:
            raise ValueError("请选择目标 SP")
        scan_result = await container.pan115.list_files_auto(scan_account, cid, user_agent, recursive=True)
        source_files = scan_result.get("files") or []
        source_provider = scan_result.get("provider") or ("115-open" if scan_account.get("accessToken") else "115-cookie")
        jobs = []
        for sf in source_files:
            if not sf.get("pickCode"):
                continue
            file_name = sf["relativePath"] or sf["name"]
            enqueue_data = {
                "profileId": profile_id,
                "sourceUrl": "",
                "sourceHeaders": {},
                "sourceProvider": source_provider,
                "sourcePickCode": sf["pickCode"],
                "sourceUserAgent": user_agent,
                "fileName": file_name,
                "remoteDir": remote_dir,
                "size": sf.get("size"),
                "sha1": sf.get("sha1"),
            }
            if source_provider == "115-open":
                enqueue_data["sourceAccessToken"] = scan_result.get("accessToken") or scan_account.get("accessToken") or ""
                enqueue_data["sourceRefreshToken"] = scan_result.get("refreshToken") or scan_account.get("refreshToken") or ""
                if scan_account.get("cookie"):
                    enqueue_data["sourceCookie"] = scan_account.get("cookie") or ""
            else:
                enqueue_data["sourceCookie"] = scan_result.get("cookie") or scan_account.get("cookie") or ""
            jobs.extend(container.jobs.enqueue_remote_url(enqueue_data))
        return {"ok": True, "total": len(source_files), "queued": len(jobs)}
    except Exception as error:
        raise_bad_request(error)
