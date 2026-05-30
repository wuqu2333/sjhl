from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from .config import DEFAULT_USER_AGENT, DOWNLOAD_DIR
from .db import Store
from .graph import GraphClient
from .pan115 import Pan115Client
from .utils import json_loads, join_remote_path, now_iso


class JobCancelled(Exception):
    pass


class TransferManager:
    def __init__(self, store: Store, graph: GraphClient, pan115: Pan115Client):
        self.store = store
        self.graph = graph
        self.pan115 = pan115
        self._runner: asyncio.Task | None = None
        self._active: dict[str, asyncio.Task] = {}
        self._stop = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._runner is not None and not self._runner.done()

    def start(self) -> None:
        if self.running:
            return
        self._stop = asyncio.Event()
        self._runner = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._runner:
            await asyncio.wait([self._runner], timeout=5)

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            self._active = {job_id: task for job_id, task in self._active.items() if not task.done()}
            settings = self.store.get_settings()
            concurrency = max(1, int(settings.get("transferConcurrency") or 4))
            slots = max(0, concurrency - len(self._active))
            if slots > 0:
                for job in self.store.claim_jobs(slots):
                    task = asyncio.create_task(self._process_one(job))
                    self._active[job["id"]] = task
            await asyncio.sleep(1.0)

    def _assert_job_alive(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        if not job:
            raise JobCancelled()
        if job.get("status") == "cancelled":
            raise JobCancelled()

    def _progress(self, job_id: str, uploaded: int, total: int, speed_bps: float, phase: str) -> None:
        self._assert_job_alive(job_id)
        percent = round(uploaded * 100 / total) if total else 100
        self.store.patch_job(
            job_id,
            {
                "uploaded": int(uploaded),
                "total": int(total),
                "percent": max(0, min(100, int(percent))),
                "speed_bps": float(speed_bps or 0),
                "phase": phase,
            },
        )

    async def _process_one(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        self.store.append_job_log(job_id, f"开始执行，第 {int(job.get('attempts') or 1)} 次尝试")
        tmp_path: Path | None = None
        try:
            profile = self.store.get_profile(job.get("profile_id") or "")
            if not profile:
                raise ValueError("SP 配置不存在")
            if not profile.get("enabled", True):
                raise ValueError("目标 SP 已停用")

            if job.get("type") == "local":
                result = await self._upload_local(job, profile)
            else:
                job = await self._refresh_down_url(job)
                tmp_path = await self._download_to_local(job)
                result = await self.graph.upload_local_file(
                    profile,
                    tmp_path,
                    job.get("remote_dir") or "",
                    job.get("file_name") or tmp_path.name,
                    int(job.get("size") or tmp_path.stat().st_size),
                    on_progress=lambda uploaded, total, speed, phase: self._progress(job_id, uploaded, total, speed, phase),
                    conflict="replace",
                )

            self._assert_job_alive(job_id)
            self.store.record_fingerprint(job, result)
            self.store.patch_job(
                job_id,
                {
                    "status": "done",
                    "phase": "完成",
                    "speed_bps": 0,
                    "percent": 100,
                    "remote_path": result.get("remotePath") or "",
                    "sha256": result.get("sha256") or job.get("sha256") or "",
                    "result": result,
                    "finished_at": now_iso(),
                },
            )
            self.store.append_job_log(job_id, "上传完成")
        except JobCancelled:
            self.store.append_job_log(job_id, "任务已取消")
        except Exception as exc:
            message = str(exc)
            self.store.append_job_log(job_id, f"失败: {message}")
            current = self.store.get_job(job_id)
            if current:
                attempts = int(current.get("attempts") or 0)
                max_attempts = int(current.get("max_attempts") or 3)
                next_status = "retry" if attempts < max_attempts else "failed"
                self.store.patch_job(
                    job_id,
                    {
                        "status": next_status,
                        "phase": "重试" if next_status == "retry" else "失败",
                        "speed_bps": 0,
                        "last_error": message,
                        "finished_at": now_iso() if next_status == "failed" else "",
                    },
                )
        finally:
            if tmp_path:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    async def _upload_local(self, job: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        job_id = job["id"]
        file_path = Path(job.get("file_path") or "")
        if not file_path.is_file():
            raise ValueError(f"本地文件不存在: {file_path}")
        size = file_path.stat().st_size
        file_name = job.get("file_name") or file_path.name
        self.store.patch_job(job_id, {"file_name": file_name, "size": size, "total": size, "phase": "上传"})
        return await self.graph.upload_local_file(
            profile,
            file_path,
            job.get("remote_dir") or "",
            file_name,
            size,
            on_progress=lambda uploaded, total, speed, phase: self._progress(job_id, uploaded, total, speed, phase),
            conflict="replace",
        )

    async def _refresh_down_url(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = job["id"]
        pick_code = job.get("source_pick_code") or ""
        if not pick_code and job.get("source_url"):
            return job
        if not pick_code:
            raise ValueError("115 pick_code 为空")
        account = self.store.get_account(job.get("account_id") or "")
        if not account:
            raise ValueError("115 账号不存在")
        self.store.patch_job(job_id, {"phase": "取链"})
        down = await self.pan115.down_url_auto(account, pick_code, account.get("user_agent") or DEFAULT_USER_AGENT)
        if down.get("accessToken") and down.get("refreshToken"):
            self.store.update_account_tokens(account["id"], down["accessToken"], down["refreshToken"])
        file_name = job.get("file_name") or down.get("fileName") or pick_code
        size = int(down.get("size") or job.get("size") or 0)
        source_provider = "115-open" if down.get("mode") == "open" else "115-cookie"
        headers = down.get("headers") or {"User-Agent": account.get("user_agent") or DEFAULT_USER_AGENT}
        patched = self.store.patch_job(
            job_id,
            {
                "source_url": down.get("url") or "",
                "source_headers": headers,
                "source_provider": source_provider,
                "file_name": file_name,
                "size": size,
                "total": size,
                "sha1": down.get("sha1") or job.get("sha1") or "",
            },
        )
        self.store.append_job_log(job_id, f"已获取 115 下载链接: {source_provider}")
        return patched or job

    async def _download_to_local(self, job: dict[str, Any]) -> Path:
        job_id = job["id"]
        settings = self.store.get_settings()
        dl_root = settings.get("downloadDir") or os.environ.get("SJHL_REWRITE_DOWNLOAD_DIR") or str(DOWNLOAD_DIR)
        tmp_dir = Path(dl_root)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        min_free_gb = max(0, int(settings.get("minFreeSpaceGb") or 0))
        if min_free_gb:
            free_gb = shutil.disk_usage(tmp_dir).free / (1024 ** 3)
            if free_gb < min_free_gb:
                raise ValueError(f"磁盘剩余空间不足: {free_gb:.1f} GB < {min_free_gb} GB")

        total_size = int(job.get("size") or 0)
        if total_size <= 0:
            raise ValueError("文件大小未知，不能开始下载")
        source_url = job.get("source_url") or ""
        if not source_url:
            raise ValueError("115 下载链接为空")
        file_name = job.get("file_name") or "remote-file"
        tmp_path = tmp_dir / f"{job_id}.download"
        downloaded = tmp_path.stat().st_size if tmp_path.exists() else 0
        if downloaded > total_size:
            tmp_path.unlink(missing_ok=True)
            downloaded = 0

        self.store.append_job_log(job_id, f"开始下载到本地临时文件: {file_name}")
        current_url = source_url
        base_headers = json_loads(job.get("source_headers"), {})
        started = time.monotonic()
        last_update_at = started
        last_update_bytes = downloaded
        refresh_count = 0
        retry_count = 0

        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
            while downloaded < total_size:
                self._assert_job_alive(job_id)
                headers = dict(base_headers)
                if downloaded > 0:
                    headers["Range"] = f"bytes={downloaded}-"
                try:
                    async with client.stream("GET", current_url, headers=headers) as response:
                        if response.status_code in (401, 403):
                            if refresh_count >= 3:
                                raise ValueError(f"115 下载链接失效，HTTP {response.status_code}")
                            refresh_count += 1
                            self.store.append_job_log(job_id, f"下载链接失效，刷新第 {refresh_count} 次")
                            job = await self._refresh_down_url(job)
                            current_url = job.get("source_url") or ""
                            base_headers = json_loads(job.get("source_headers"), {})
                            continue
                        if downloaded > 0 and response.status_code == 200:
                            downloaded = 0
                            tmp_path.unlink(missing_ok=True)
                        if response.status_code >= 400:
                            raise ValueError(f"下载失败 HTTP {response.status_code}")

                        mode = "ab" if downloaded > 0 else "wb"
                        with tmp_path.open(mode) as stream:
                            async for chunk in response.aiter_bytes(chunk_size=4 * 1024 * 1024):
                                self._assert_job_alive(job_id)
                                if not chunk:
                                    continue
                                stream.write(chunk)
                                downloaded += len(chunk)
                                now = time.monotonic()
                                if now - last_update_at >= 1.0:
                                    delta_bytes = downloaded - last_update_bytes
                                    delta_time = max(now - last_update_at, 0.001)
                                    self._progress(job_id, downloaded, total_size, delta_bytes / delta_time, "下载")
                                    last_update_at = now
                                    last_update_bytes = downloaded
                        retry_count = 0
                        refresh_count = 0
                except (httpx.RemoteProtocolError, httpx.ReadError, httpx.TimeoutException, httpx.NetworkError, ValueError) as exc:
                    if downloaded >= total_size:
                        break
                    retry_count += 1
                    if retry_count > 6:
                        raise ValueError(f"下载中断重试耗尽: {exc}") from exc
                    self.store.append_job_log(job_id, f"下载中断，{retry_count}/6 次重试: {exc}")
                    await asyncio.sleep(min(30, retry_count * 3))

        elapsed = max(time.monotonic() - started, 0.001)
        speed = total_size / elapsed
        self._progress(job_id, total_size, total_size, speed, "下载完成")
        self.store.append_job_log(job_id, f"下载完成，平均速度 {speed / 1024 / 1024:.1f} MB/s，开始上传")
        return tmp_path

    def create_115_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.create_job(
            {
                "type": "115",
                "profile_id": payload.get("profile_id") or payload.get("profileId"),
                "account_id": payload.get("account_id") or payload.get("accountId"),
                "pickCode": payload.get("pickCode") or payload.get("pick_code"),
                "fileName": payload.get("fileName") or payload.get("file_name") or "remote-file",
                "remoteDir": payload.get("remoteDir") or payload.get("remote_dir") or "",
                "size": int(payload.get("size") or 0),
                "maxAttempts": int(payload.get("maxAttempts") or 3),
                "sourceProvider": "115-open",
            }
        )

    def create_local_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(payload.get("filePath") or payload.get("file_path") or "")
        file_name = payload.get("fileName") or payload.get("file_name") or file_path.name
        size = file_path.stat().st_size if file_path.is_file() else int(payload.get("size") or 0)
        return self.store.create_job(
            {
                "type": "local",
                "profile_id": payload.get("profile_id") or payload.get("profileId"),
                "filePath": str(file_path),
                "fileName": file_name,
                "remoteDir": payload.get("remoteDir") or payload.get("remote_dir") or "",
                "size": size,
                "maxAttempts": int(payload.get("maxAttempts") or 3),
            }
        )

