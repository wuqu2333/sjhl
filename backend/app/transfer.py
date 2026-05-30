from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .capacity import is_capacity_pool_profile_id, pool_id_from_profile_id
from .db import AppDatabase, json_dumps, json_loads, new_id
from .pan115 import DEFAULT_UA
from .utils import (
    collect_local_files,
    hash_file,
    join_remote_path,
    normalize_remote_dir,
    relative_remote_dir,
    safe_file_name_from_url,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


LOCAL_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


class JobCancelled(Exception):
    pass


def local_day_range_utc() -> tuple[str, str]:
    now = datetime.now(LOCAL_TZ)
    start = datetime(now.year, now.month, now.day, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


def next_local_day_start_utc() -> str:
    now = datetime.now(LOCAL_TZ)
    tomorrow = datetime(now.year, now.month, now.day, tzinfo=LOCAL_TZ) + timedelta(days=1)
    return tomorrow.astimezone(timezone.utc).isoformat()


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(max(0, int(value or 0)))
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.0f} {units[unit]}" if size >= 10 or unit == 0 else f"{size:.1f} {units[unit]}"


def error_message(error: Exception) -> str:
    message = str(error).strip()
    if message:
        return message
    return f"{error.__class__.__name__}: no detail"


def retry_delay_seconds(message: str, attempts: int) -> int:
    text = message.lower()
    if "refresh frequently" in text or "刷新过于频繁" in message or "过于频繁" in message:
        return 15 * 60
    if "peer closed connection" in text or "source stream interrupted" in text or "源文件读取中断" in message:
        return min(30 * 60, max(5 * 60, attempts * 5 * 60))
    if "download url refresh failed" in text or "下载链接" in message:
        return min(20 * 60, max(2 * 60, attempts * 2 * 60))
    if "disk space" in text or "磁盘空间不足" in text:
        return min(30 * 60, max(5 * 60, attempts * 5 * 60))
    return min(30 * 60, max(30, 30 * attempts))


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    safe = dict(job)
    safe["hasSourceUrl"] = bool(safe.get("source_url"))
    safe["hasSourceCookie"] = bool(safe.get("source_cookie"))
    safe["hasSourceAccessToken"] = bool(safe.get("source_access_token"))
    safe["hasSourceRefreshToken"] = bool(safe.get("source_refresh_token"))
    safe.pop("source_url", None)
    safe.pop("source_cookie", None)
    safe.pop("source_access_token", None)
    safe.pop("source_refresh_token", None)
    safe.pop("source_headers", None)
    safe["staged"] = bool(safe.get("staged_path", ""))
    safe.pop("staged_path", None)
    safe["progress"] = {
        "uploaded": int(safe.get("uploaded") or 0),
        "downloaded": int(safe.get("downloaded") or 0),
        "total": int(safe.get("total") or 0),
        "percent": int(safe.get("percent") or 0),
    }
    dl_speed = safe.get("download_speed")
    safe["download_speed"] = int(dl_speed) if dl_speed is not None else 0
    uploaded = int(safe.get("uploaded") or 0)
    started = safe.get("started_at", "")
    updated = safe.get("updated_at", "")
    if started and updated and uploaded > 0:
        try:
            from datetime import datetime, timezone
            start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            update_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            secs = (update_dt - start_dt).total_seconds()
            if secs > 0:
                safe["speed"] = int(uploaded / secs)
        except Exception:
            pass
    safe["logs"] = json_loads(safe.get("logs"), [])
    return safe


class TransferJobStore:
    def __init__(self, database: AppDatabase):
        self.db = database

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        created = now_iso()
        row = {
            "id": data.get("id") or new_id(),
            "type": data.get("type"),
            "status": data.get("status") or "queued",
            "requested_profile_id": data.get("requestedProfileId") or data.get("profileId") or "",
            "profile_id": data.get("profileId") or "",
            "profile_name": data.get("profileName") or "",
            "file_path": data.get("filePath") or "",
            "source_url": data.get("sourceUrl") or "",
            "source_headers": json_dumps(data.get("sourceHeaders") or {}),
            "source_provider": data.get("sourceProvider") or "",
            "source_pick_code": data.get("sourcePickCode") or "",
            "source_cookie": data.get("sourceCookie") or "",
            "source_access_token": data.get("sourceAccessToken") or "",
            "source_refresh_token": data.get("sourceRefreshToken") or "",
            "source_user_agent": data.get("sourceUserAgent") or "",
            "file_name": data.get("fileName") or "",
            "remote_dir": data.get("remoteDir") or "",
            "remote_path": data.get("remotePath") or "",
            "size": int(data.get("size") or 0),
            "sha1": data.get("sha1") or "",
            "sha256": data.get("sha256") or "",
            "conflict_behavior": data.get("conflictBehavior") or "replace",
            "dedupe_scope": data.get("dedupeScope") or "global",
            "uploaded": int((data.get("progress") or {}).get("uploaded") or 0),
            "total": int((data.get("progress") or {}).get("total") or data.get("size") or 0),
            "percent": int((data.get("progress") or {}).get("percent") or 0),
            "attempts": int(data.get("attempts") or 0),
            "max_attempts": int(data.get("maxAttempts") or 3),
            "next_attempt_at": data.get("nextAttemptAt") or "",
            "last_error": data.get("lastError") or "",
            "logs": json.dumps(data.get("logs") or [], ensure_ascii=False),
            "result": json_dumps(data.get("result") or {}),
            "created_at": created,
            "updated_at": created,
            "started_at": "",
            "finished_at": "",
        }
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        self.db.execute(f"INSERT INTO transfer_jobs ({columns}) VALUES ({placeholders})", list(row.values()))
        return row

    def list(self, limit: int = 200, include_secrets: bool = False) -> list[dict[str, Any]]:
        jobs = self.db.query(
            """
            SELECT * FROM transfer_jobs
            ORDER BY
              CASE status
                WHEN 'running' THEN 0
                WHEN 'queued' THEN 1
                WHEN 'retry' THEN 2
                WHEN 'failed' THEN 3
                ELSE 4
              END,
              updated_at DESC,
              created_at DESC
            LIMIT ?
            """,
            [limit],
        )
        return jobs if include_secrets else [public_job(job) for job in jobs]

    def status_counts(self) -> dict[str, int]:
        rows = self.db.query(
            """
            SELECT status, COUNT(*) AS count
            FROM transfer_jobs
            GROUP BY status
            ORDER BY status
            """
        )
        return {str(row.get("status") or ""): int(row.get("count") or 0) for row in rows}

    def update_115_open_tokens(self, old_access_token: str, old_refresh_token: str, access_token: str, refresh_token: str) -> int:
        if not access_token and not refresh_token:
            return 0
        clauses = []
        values: list[Any] = []
        if old_access_token:
            clauses.append("source_access_token = ?")
            values.append(old_access_token)
        if old_refresh_token:
            clauses.append("source_refresh_token = ?")
            values.append(old_refresh_token)
        if not clauses:
            return 0
        values = [
            access_token,
            refresh_token,
            now_iso(),
            *values,
        ]
        self.db.execute(
            f"""
            UPDATE transfer_jobs
            SET source_access_token = ?,
                source_refresh_token = ?,
                updated_at = ?
            WHERE source_provider = '115-open'
              AND status IN ('queued', 'retry', 'running', 'failed')
              AND ({" OR ".join(clauses)})
            """,
            values,
        )
        rows = self.db.query(
            f"""
            SELECT COUNT(*) AS count
            FROM transfer_jobs
            WHERE source_provider = '115-open'
              AND status IN ('queued', 'retry', 'running', 'failed')
              AND source_access_token = ?
              AND source_refresh_token = ?
            """,
            [access_token, refresh_token],
        )
        return int((rows[0] if rows else {}).get("count") or 0)

    def completed_stats(self, start_iso: str, end_iso: str) -> dict[str, int]:
        rows = self.db.query(
            """
            SELECT COUNT(*) AS file_count, COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE size END), 0) AS total_size
            FROM transfer_jobs
            WHERE status = 'done' AND finished_at >= ? AND finished_at < ?
            """,
            [start_iso, end_iso],
        )
        row = rows[0] if rows else {}
        return {
            "fileCount": int(row.get("file_count") or 0),
            "totalSize": int(row.get("total_size") or 0),
        }

    def running_reserved_size(self) -> int:
        rows = self.db.query(
            """
            SELECT COALESCE(SUM(CASE WHEN total > 0 THEN total ELSE size END), 0) AS total_size
            FROM transfer_jobs
            WHERE status = 'running'
            """
        )
        return int((rows[0] if rows else {}).get("total_size") or 0)

    def defer_until(self, job_id: str, reason: str, next_attempt_at: str) -> None:
        self.patch(
            job_id,
            {
                "status": "queued",
                "last_error": reason,
                "next_attempt_at": next_attempt_at,
            },
        )

    def next_queued(self, limit: int) -> list[dict[str, Any]]:
        return self.db.query(
            """
            SELECT * FROM transfer_jobs
            WHERE status IN ('queued', 'retry') AND staged_path = ''
              AND (next_attempt_at = '' OR next_attempt_at <= ?)
            ORDER BY
              CASE status WHEN 'queued' THEN 0 ELSE 1 END,
              CASE WHEN next_attempt_at = '' THEN created_at ELSE next_attempt_at END ASC,
              created_at ASC
            LIMIT ?
            """,
            [now_iso(), limit],
        )

    def next_staged(self, limit: int) -> list[dict[str, Any]]:
        """返回已下载暂存、等待上传的任务。"""
        return self.db.query(
            """
            SELECT * FROM transfer_jobs
            WHERE status = 'queued' AND staged_path != ''
              AND (next_attempt_at = '' OR next_attempt_at <= ?)
            ORDER BY created_at ASC
            LIMIT ?
            """,
            [now_iso(), limit],
        )

    def mark_staged(self, job_id: str, staged_path: str) -> dict[str, Any] | None:
        """标记下载完成，状态回到 queued 等待上传池认领。"""
        self.db.execute(
            "UPDATE transfer_jobs SET status = 'queued', staged_path = ?, updated_at = ? WHERE id = ?",
            [staged_path, now_iso(), job_id],
        )
        return self.get(job_id)

    def requeue_running(self) -> None:
        self.db.execute(
            """
            UPDATE transfer_jobs
            SET status = 'retry',
                last_error = '后端重启，任务已重新排队',
                next_attempt_at = '',
                staged_path = '',
                updated_at = ?
            WHERE status = 'running'
            """,
            [now_iso()],
        )

    def get(self, job_id: str) -> dict[str, Any] | None:
        rows = self.db.query("SELECT * FROM transfer_jobs WHERE id = ?", [job_id])
        return rows[0] if rows else None

    def exists(self, job_id: str) -> bool:
        rows = self.db.query("SELECT 1 AS found FROM transfer_jobs WHERE id = ? LIMIT 1", [job_id])
        return bool(rows)

    def patch(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get(job_id)
        if not current:
            return None
        next_row = {**current, **patch, "updated_at": now_iso()}
        if "progress" in patch:
            next_row["uploaded"] = int(patch["progress"].get("uploaded") or 0)
            next_row["downloaded"] = int(patch["progress"].get("downloaded") or 0)
            next_row["total"] = int(patch["progress"].get("total") or next_row.get("size") or 0)
            next_row["percent"] = int(patch["progress"].get("percent") or 0)
        next_row.pop("progress", None)
        for key in ("logs", "result", "source_headers"):
            if isinstance(next_row.get(key), (list, dict)):
                next_row[key] = json.dumps(next_row[key], ensure_ascii=False)
        assignments = ", ".join(f"{key} = ?" for key in next_row.keys() if key != "id")
        values = [value for key, value in next_row.items() if key != "id"] + [job_id]
        self.db.execute(f"UPDATE transfer_jobs SET {assignments} WHERE id = ?", values)
        return self.get(job_id)

    def patch_progress(self, job_id: str, uploaded: int, total: int, downloaded: int | None = None) -> None:
        """轻量进度更新：仅 UPDATE 变更字段，不传入则不修改。"""
        fields = ["uploaded = ?", "total = ?", "percent = ?", "updated_at = ?"]
        values = [uploaded, total, round(uploaded / total * 100) if total else 0, now_iso()]
        if downloaded is not None:
            fields.insert(2, "downloaded = ?")
            values.insert(2, downloaded)
        values.append(job_id)
        self.db.execute(f"UPDATE transfer_jobs SET {', '.join(fields)} WHERE id = ?", values)

    def append_log(self, job_id: str, message: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        logs = json_loads(job.get("logs"), [])
        logs.append({"at": now_iso(), "message": message})
        self.patch(job_id, {"logs": logs[-50:]})

    def mark_running(self, job_id: str) -> dict[str, Any] | None:
        job = self.get(job_id)
        if not job:
            return None
        return self.patch(
            job_id,
            {
                "status": "running",
                "attempts": int(job.get("attempts") or 0) + 1,
                "started_at": now_iso(),
                "finished_at": "",
                "next_attempt_at": "",
                "last_error": "",
                "progress": {"uploaded": 0, "total": int(job.get("size") or job.get("total") or 0), "percent": 0},
            },
        )

    def mark_done(self, job_id: str) -> None:
        self.patch(job_id, {"status": "done", "finished_at": now_iso(), "last_error": ""})

    def delete(self, job_id: str) -> bool:
        if not self.exists(job_id):
            return False
        self.db.execute("DELETE FROM transfer_jobs WHERE id = ?", [job_id])
        return True

    def delete_completed(self) -> int:
        rows = self.db.query(
            """
            SELECT COUNT(*) AS count
            FROM transfer_jobs
            WHERE status IN ('done', 'skipped', 'cancelled')
            """
        )
        count = int((rows[0] if rows else {}).get("count") or 0)
        if count:
            self.db.execute("DELETE FROM transfer_jobs WHERE status IN ('done', 'skipped', 'cancelled')")
        return count

    def mark_failed_or_retry(self, job_id: str, error: Exception) -> None:
        job = self.get(job_id)
        if not job:
            return
        attempts = int(job.get("attempts") or 0)
        max_attempts = int(job.get("max_attempts") or 3)
        retry = attempts < max_attempts
        message = error_message(error)
        delay_seconds = retry_delay_seconds(message, attempts)
        self.patch(
            job_id,
            {
                "status": "retry" if retry else "failed",
                "last_error": message,
                "next_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
                if retry
                else "",
                "finished_at": "" if retry else now_iso(),
                "staged_path": "",
            },
        )


class JobQueue:
    def __init__(
        self,
        profile_store,
        dedupe_store,
        graph_client,
        capacity_service,
        job_store: TransferJobStore,
        pan115_client,
        concurrency: int = 2,
        settings_store=None,
        pan115_accounts_store=None,
    ):
        self.profile_store = profile_store
        self.dedupe_store = dedupe_store
        self.graph = graph_client
        self.capacity = capacity_service
        self.jobs = job_store
        self.pan115 = pan115_client
        self.settings = settings_store
        self.pan115_accounts = pan115_accounts_store
        self.concurrency = max(1, concurrency)
        self.running = False
        self._process_lock = asyncio.Lock()
        self._process_scheduled = False
        self._scheduler_started = False

    def start_scheduler(self) -> None:
        """启动定时器，每 10 秒检查一次待处理任务。workerMode 下跳过本地执行。"""
        if self._scheduler_started:
            return
        self.jobs.requeue_running()
        self._scheduler_started = True

        async def tick():
            while True:
                await asyncio.sleep(10)
                if self._worker_mode_enabled():
                    continue
                try:
                    await self.process()
                except Exception as e:
                    from utils.logging import logger
                    logger.error(f"传输调度器错误: {e}")

        import asyncio as _asyncio
        task = _asyncio.ensure_future(tick())
        self._tick_task = task

    def _worker_mode_enabled(self) -> bool:
        if not self.settings:
            return False
        try:
            return bool(self.settings.get().get("workerMode", False))
        except Exception:
            return False

    def list(self, limit: int = 200):
        return self.jobs.list(limit)

    def status_counts(self) -> dict[str, int]:
        return self.jobs.status_counts()

    def delete(self, job_id: str) -> bool:
        return self.jobs.delete(job_id)

    def clear_completed(self) -> int:
        return self.jobs.delete_completed()

    def effective_concurrency(self) -> int:
        if not self.settings:
            return self.concurrency
        try:
            return max(1, int(self.settings.get().get("transferConcurrency") or self.concurrency))
        except Exception:
            return self.concurrency

    def schedule_process(self) -> None:
        if self._process_scheduled:
            return
        self._process_scheduled = True

        async def run_later():
            await asyncio.sleep(0)
            self._process_scheduled = False
            await self.process()

        asyncio.ensure_future(run_later())

    def choose_profile(self, profile_id: str, size: int) -> dict[str, Any]:
        if is_capacity_pool_profile_id(profile_id):
            return self.capacity.choose_profile(size, pool_id_from_profile_id(profile_id))
        profile = self.profile_store.get(profile_id)
        if not profile:
            raise ValueError("未找到 SP 配置")
        return profile

    def enqueue_local(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        base_path, files = collect_local_files(data["localPath"], bool(data.get("recursive")))
        created = []
        for file_path in files:
            stat = file_path.stat()
            profile = self.choose_profile(data["profileId"], stat.st_size)
            remote_dir = normalize_remote_dir(
                "/".join(part for part in [profile.get("rootPath"), relative_remote_dir(data.get("remoteDir", ""), base_path, file_path)] if part)
            )
            file_name = file_path.name
            remote_path = join_remote_path(remote_dir, file_name)
            duplicate = self.dedupe_store.find(file_name, stat.st_size)
            if duplicate:
                created.append(
                    self.jobs.create(
                        {
                            "type": "local",
                            "status": "skipped",
                            "profileId": profile["id"],
                            "profileName": profile["name"],
                            "filePath": str(file_path),
                            "fileName": file_name,
                            "remoteDir": remote_dir,
                            "remotePath": remote_path,
                            "size": stat.st_size,
                            "logs": [{"at": now_iso(), "message": "全局重复，已跳过"}],
                            "progress": {"uploaded": stat.st_size, "total": stat.st_size, "percent": 100},
                        }
                    )
                )
                continue
            created.append(
                self.jobs.create(
                    {
                        "type": "local",
                        "requestedProfileId": data["profileId"],
                        "profileId": profile["id"],
                        "profileName": profile["name"],
                        "filePath": str(file_path),
                        "fileName": file_name,
                        "remoteDir": remote_dir,
                        "remotePath": remote_path,
                        "size": stat.st_size,
                        "dedupeScope": data.get("dedupeScope", "global"),
                        "conflictBehavior": data.get("conflictBehavior", "fail"),
                    }
                )
            )
        self.schedule_process()
        return [public_job(job) for job in created]

    def enqueue_remote_url(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        size = int(data.get("size") or 0)
        profile = self.choose_profile(data["profileId"], size)
        source_url = data.get("sourceUrl") or ""
        file_name = data.get("fileName") or (safe_file_name_from_url(source_url) if source_url else data.get("sourcePickCode") or "remote-file")
        remote_dir = normalize_remote_dir("/".join(part for part in [profile.get("rootPath"), data.get("remoteDir", "")] if part))
        remote_path = join_remote_path(remote_dir, file_name)
        if size and self.dedupe_store.find(file_name, size):
            job = self.jobs.create(
                {
                    "type": "115-url",
                    "status": "skipped",
                    "profileId": profile["id"],
                    "profileName": profile["name"],
                    "sourceUrl": source_url,
                    "fileName": file_name,
                    "remotePath": remote_path,
                    "size": size,
                    "logs": [{"at": now_iso(), "message": "全局重复，已跳过"}],
                }
            )
            return [public_job(job)]
        job = self.jobs.create(
            {
                "type": "115-url",
                "requestedProfileId": data["profileId"],
                "profileId": profile["id"],
                "profileName": profile["name"],
                "sourceUrl": source_url,
                "sourceHeaders": data.get("sourceHeaders") or {},
                "sourceProvider": data.get("sourceProvider") or "",
                "sourcePickCode": data.get("sourcePickCode") or "",
                "sourceCookie": data.get("sourceCookie") or "",
                "sourceAccessToken": data.get("sourceAccessToken") or "",
                "sourceRefreshToken": data.get("sourceRefreshToken") or "",
                "sourceUserAgent": data.get("sourceUserAgent") or "",
                "fileName": file_name,
                "remoteDir": remote_dir,
                "remotePath": remote_path,
                "size": size,
                "dedupeScope": data.get("dedupeScope", "global"),
                "conflictBehavior": data.get("conflictBehavior", "fail"),
            }
        )
        self.schedule_process()
        return [public_job(job)]

    async def process(self):
        if self._process_lock.locked():
            return
        from utils.logging import logger
        try:
            async with self._process_lock:
                concurrency = self.effective_concurrency()
                running: dict[asyncio.Task, str] = {}  # 共享槽位池

                while True:
                    # 共享 concurrency 个槽位，优先上传已暂存的任务
                    while len(running) < concurrency:
                        claimed = False
                        # 优先上传
                        staged = self.jobs.next_staged(1)
                        if staged:
                            runnable = self._filter_daily_quota(staged)
                            if runnable:
                                job = runnable[0]
                                sp = job.get("staged_path", "")
                                if sp and self.jobs.patch(job["id"], {"status": "running", "staged_path": ""}):
                                    task = asyncio.ensure_future(self._upload_one(job, sp))
                                    running[task] = job["id"]
                                    claimed = True
                        if claimed:
                            continue
                        # 其次下载
                        queued = self.jobs.next_queued(1)
                        if queued:
                            runnable = self._filter_daily_quota(queued)
                            if runnable:
                                job = runnable[0]
                                claimed_job = self.jobs.mark_running(job["id"])
                                if claimed_job:
                                    task = asyncio.ensure_future(self._download_one(claimed_job))
                                    running[task] = job["id"]
                                    claimed = True
                        if not claimed:
                            break

                    if not running:
                        return

                    counts = self.jobs.status_counts()
                    logger.info(
                        f"传输队列：运行中={len(running)}/{concurrency}，"
                        f"排队={counts.get('queued', 0)}，重试={counts.get('retry', 0)}，"
                        f"已完成={counts.get('done', 0)}，失败={counts.get('failed', 0)}"
                    )

                    done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                    running = {t: running[t] for t in (set(running.keys()) - done)}

                    for t in done:
                        result = None
                        if not t.cancelled():
                            try:
                                result = await t
                            except Exception:
                                pass
                        # 下载完成 → 标记暂存等待上传
                        if result and isinstance(result, tuple) and len(result) == 2:
                            jid, spath = result
                            if spath and self.jobs.exists(jid):
                                self.jobs.mark_staged(jid, spath)
        except Exception:
            logger.exception("传输调度器异常退出，10 秒后重试")
            await asyncio.sleep(10)
            self._process_scheduled = False
            self.schedule_process()

    def _filter_daily_quota(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.settings:
            return jobs
        settings = self.settings.get()
        if not settings.get("dailyUploadLimitEnabled"):
            return jobs
        limit = int(settings.get("dailyUploadLimitBytes") or 0)
        if limit <= 0:
            return jobs
        start, end = local_day_range_utc()
        completed = self.jobs.completed_stats(start, end)["totalSize"]
        reserved = completed + self.jobs.running_reserved_size()
        runnable: list[dict[str, Any]] = []
        for job in jobs:
            size = int(job.get("total") or job.get("size") or 0)
            if size > 0 and reserved + size > limit:
                reason = f"今日上传量已达上限：已用/预占 {format_bytes(reserved)}，上限 {format_bytes(limit)}"
                self.jobs.defer_until(job["id"], reason, next_local_day_start_utc())
                continue
            reserved += size
            runnable.append(job)
        return runnable

    async def _download_one(self, job: dict[str, Any]) -> tuple[str, str] | None:
        """只下载到本地暂存，返回 (job_id, staged_path)，不执行上传。"""
        job_id = job["id"]
        try:
            if job["type"] == "local":
                # 本地文件不需要下载，file_path 即为暂存路径
                self.jobs.mark_staged(job_id, job["file_path"])
                return (job_id, job["file_path"])
            job = await self._refresh_down_url(job)
            if not job or not self.jobs.exists(job_id):
                raise JobCancelled()
            tmp_path = await self._download_to_local(job, job_id)
            self.jobs.mark_staged(job_id, str(tmp_path))
            self.jobs.append_log(job_id, "下载完成，等待上传")
            return (job_id, str(tmp_path))
        except JobCancelled:
            return None
        except Exception as error:
            from utils.logging import logger
            logger.warning(f"下载失败 job={job_id} file={job.get('file_name','')}: {error_message(error)}")
            self.jobs.append_log(job_id, str(error))
            self.jobs.mark_failed_or_retry(job_id, error)
            return None

    async def _upload_one(self, job: dict[str, Any], staged_path: str):
        """上传暂存文件到 SP，完成后清理临时文件。"""
        job_id = job["id"]

        def update_progress(uploaded: int, total: int) -> None:
            if not self.jobs.exists(job_id):
                raise JobCancelled()
            self.jobs.patch_progress(job_id, uploaded, total)

        try:
            profile = self.profile_store.get(job["profile_id"])
            if not profile:
                raise ValueError("SP 配置已不存在")
            result = await self.graph.upload_local_file(
                profile, staged_path, job["remote_dir"], job["file_name"],
                int(job["size"]), job["conflict_behavior"], update_progress,
            )
            if not self.jobs.exists(job_id):
                raise JobCancelled()
            if job["type"] == "local":
                self._record_local(job, result)
            else:
                self._record_remote(job, result)
            self.jobs.mark_done(job_id)
            self.jobs.append_log(job_id, "上传完成")
            await self.capacity.refresh_quota(profile)
        except JobCancelled:
            pass
        except Exception as error:
            from utils.logging import logger
            logger.warning(f"上传失败 job={job_id} file={job.get('file_name','')}: {error_message(error)}")
            self.jobs.append_log(job_id, str(error))
            self.jobs.mark_failed_or_retry(job_id, error)
        finally:
            if job["type"] != "local":
                try:
                    Path(staged_path).unlink(missing_ok=True)
                except Exception:
                    pass
            import gc
            gc.collect()

    async def _refresh_down_url(self, job: dict[str, Any]) -> dict[str, Any]:
        from utils.logging import logger
        # 已有 URL 直接用，只在重试时才刷新
        if job.get("source_provider") == "115-cookie":
            cookie = job.get("source_cookie", "")
            pick_code = job.get("source_pick_code", "")
            user_agent = job.get("source_user_agent", DEFAULT_UA)
            try:
                down = await self.pan115.down_url_by_cookie(cookie, pick_code, user_agent)
            except Exception:
                raise ValueError(f"115 下载链接获取失败，Cookie 可能已过期")
            headers = down.get("headers") or {}
            headers.setdefault("Cookie", cookie)
            return self.jobs.patch(job["id"], {"source_url": down["url"], "source_headers": headers})
        if job.get("source_provider") == "115-open":
            pick_code = job.get("source_pick_code", "")
            user_agent = job.get("source_user_agent", DEFAULT_UA)
            old_access_token = job.get("source_access_token", "")
            old_refresh_token = job.get("source_refresh_token", "")
            source_headers: dict[str, str] = {}
            # 优先使用 cookie 方式获取下载链接（CDN headers 更完整）
            cookie = job.get("source_cookie", "")
            if not cookie and self.pan115_accounts:
                accounts = self.pan115_accounts.list_with_secrets() if hasattr(self.pan115_accounts, "list_with_secrets") else []
                for acct in accounts:
                    if acct.get("cookie") and (
                        acct.get("accessToken") == old_access_token
                        or acct.get("refreshToken") == old_refresh_token
                    ):
                        cookie = acct["cookie"]
                        break
            if cookie:
                try:
                    down = await self.pan115.down_url_by_cookie(cookie, pick_code, user_agent)
                    source_headers = down.get("headers") or {}
                    source_headers.setdefault("Cookie", cookie)
                    logger.info(f"115 使用 Cookie 获取下载链接成功：{pick_code}")
                except Exception as e:
                    logger.warning(f"115 Cookie 下载链接获取失败，回退 Open API：{e}")
                    down = None
                if down:
                    next_size = int(down.get("size") or job.get("size") or 0)
                    return self.jobs.patch(
                        job["id"],
                        {
                            "source_url": down["url"],
                            "source_headers": source_headers,
                            "file_name": down.get("fileName") or job.get("file_name", ""),
                            "size": next_size,
                            "total": next_size,
                        },
                    )
            # 回退到 Open API
            try:
                down = await self.pan115.down_url(old_access_token, pick_code, user_agent, old_refresh_token)
            except Exception as error:
                raise ValueError(f"115 Open 下载链接刷新失败：{error}") from error
            next_file_name = job.get("file_name", "")
            if down.get("fileName") and next_file_name in ("", pick_code, "remote-file"):
                next_file_name = down["fileName"]
            next_size = int(down.get("size") or job.get("size") or 0)
            next_access_token = down.get("accessToken") or old_access_token
            next_refresh_token = down.get("refreshToken") or old_refresh_token
            if (next_access_token and next_access_token != old_access_token) or (next_refresh_token and next_refresh_token != old_refresh_token):
                self.jobs.update_115_open_tokens(old_access_token, old_refresh_token, next_access_token, next_refresh_token)
                if self.pan115_accounts and hasattr(self.pan115_accounts, "update_open_tokens"):
                    self.pan115_accounts.update_open_tokens(old_access_token, old_refresh_token, next_access_token, next_refresh_token)
            source_headers_fallback = down.get("headers") or {"user-agent": user_agent}
            return self.jobs.patch(
                job["id"],
                {
                    "source_url": down["url"],
                    "source_headers": source_headers_fallback,
                    "source_access_token": next_access_token,
                    "source_refresh_token": next_refresh_token,
                    "file_name": next_file_name,
                    "size": next_size,
                    "total": next_size,
                },
            )
        if not job.get("source_url"):
            raise ValueError("远程源下载链接为空")
        return job

    async def _download_to_local(self, job: dict[str, Any], job_id: str) -> Path:
        """下载远程文件到本地临时目录，返回文件路径。"""
        from config.settings import DATA_DIR
        dl_root = os.environ.get("SJHL_DOWNLOAD_DIR", "")
        if not dl_root and self.settings:
            try:
                dl_root = self.settings.get().get("downloadDir", "")
            except Exception:
                pass
        if dl_root:
            tmp_dir = Path(dl_root)
        else:
            tmp_dir = DATA_DIR / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # 磁盘空间检查：使用用户设置的阈值，默认 2GB
        import shutil
        try:
            free_gb = shutil.disk_usage(tmp_dir).free / (1024 ** 3)
            threshold = max(0, int(self.settings.get().get("minFreeSpaceGb", 2) or 2))
            if threshold > 0 and free_gb < threshold:
                raise ValueError(f"磁盘空间不足 ({free_gb:.1f} GB < {threshold} GB)，暂停下载等待空间释放")
        except ValueError:
            raise
        except Exception:
            pass

        tmp_path = tmp_dir / f"{job_id}.download"
        file_name = job.get("file_name", "unknown")
        total_size = int(job.get("size") or 0)
        source_url = job.get("source_url", "")
        base_headers = json_loads(job.get("source_headers") or "{}", {})
        current_url = source_url

        if not source_url:
            raise ValueError("下载链接为空")
        if total_size <= 0:
            raise ValueError("文件大小未知")

        self.jobs.append_log(job_id, f"开始下载到本地: {file_name} ({total_size / 1024 / 1024:.0f} MiB)")
        from utils.logging import logger

        downloaded = 0
        refresh_count = 0
        retry_count = 0
        started = time.time()
        last_progress_update = 0.0

        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
            while downloaded < total_size:
                headers = dict(base_headers)
                if downloaded > 0:
                    headers["Range"] = f"bytes={downloaded}-"
                try:
                    async with client.stream("GET", current_url, headers=headers) as response:
                        if response.status_code in (401, 403):
                            if refresh_count < 3:
                                refresh_count += 1
                                logger.warning(f"下载链接过期，刷新中 ({refresh_count}/3): {file_name}")
                                job = await self._refresh_down_url(job)
                                if not job or not self.jobs.exists(job_id):
                                    raise JobCancelled()
                                current_url = job.get("source_url", "")
                                base_headers = json_loads(job.get("source_headers") or "{}", {})
                                retry_count = 0
                                continue
                            raise ValueError(f"下载链接失效且无法刷新，HTTP {response.status_code}")
                        if response.status_code >= 400:
                            raise ValueError(f"下载失败 HTTP {response.status_code}")
                        with open(tmp_path, "ab" if downloaded > 0 else "wb") as f:
                            async for data in response.aiter_bytes(chunk_size=4 * 1024 * 1024):
                                f.write(data)
                                downloaded += len(data)
                                now = time.time()
                                if now - last_progress_update > 5:
                                    elapsed = now - started
                                    speed = downloaded / elapsed if elapsed > 0 else 0
                                    pct = round(downloaded * 100 / total_size) if total_size else 0
                                    self.jobs.patch(job_id,
                                        {"progress": {"downloaded": downloaded, "total": total_size, "percent": pct},
                                         "download_speed": int(speed)})
                                    logger.info(
                                        f"下载进度: {file_name} {downloaded / 1024 / 1024:.0f}/{total_size / 1024 / 1024:.0f} MiB "
                                        f"({pct}%) {speed / 1024 / 1024:.1f} MiB/s"
                                    )
                                    last_progress_update = now
                        retry_count = 0
                        refresh_count = 0
                except (httpx.RemoteProtocolError, httpx.ReadError, httpx.TimeoutException, httpx.NetworkError, ValueError, JobCancelled) as e:
                    if isinstance(e, JobCancelled):
                        raise
                    if downloaded >= total_size:
                        break
                    retry_count += 1
                    if retry_count > 6:
                        raise ValueError(f"下载中断重试耗尽: {e}")
                    delay = min(30, retry_count * 3)
                    logger.warning(f"下载中断，重试 {retry_count}/6: {file_name}, {e}")
                    await asyncio.sleep(delay)

        elapsed = time.time() - started
        speed = total_size / elapsed / 1024 / 1024 if elapsed > 0 else 0
        logger.info(f"下载完成: {file_name} {total_size / 1024 / 1024:.0f} MiB / {elapsed:.1f}s / {speed:.1f} MiB/s")
        self.jobs.append_log(job_id, f"下载完成，开始上传 ({speed:.1f} MiB/s)")
        return tmp_path

    def _record_local(self, job: dict[str, Any], result: dict[str, Any]) -> None:
        self.dedupe_store.record(
            {
                "size": job["size"],
                "sourceType": "local",
                "profileId": job["profile_id"],
                "remotePath": result["remotePath"],
                "fileName": job["file_name"],
            }
        )

    def _record_remote(self, job: dict[str, Any], result: dict[str, Any]) -> None:
        self.dedupe_store.record(
            {
                "size": result["size"],
                "sourceType": "115-url",
                "profileId": job["profile_id"],
                "remotePath": result["remotePath"],
                "fileName": job["file_name"],
            }
        )

    # ── Worker API methods ──────────────────────────────────────────

    def list_worker_available(self, limit: int = 50) -> list[dict[str, Any]]:
        """返回可供 worker 执行的待处理任务（含下载链接）。"""
        from utils.logging import logger

        jobs = self.jobs.db.query(
            """
            SELECT * FROM transfer_jobs
            WHERE status IN ('queued', 'retry')
              AND staged_path = ''
              AND (next_attempt_at = '' OR next_attempt_at <= ?)
            ORDER BY
              CASE status WHEN 'queued' THEN 0 ELSE 1 END,
              created_at ASC
            LIMIT ?
            """,
            [now_iso(), limit],
        )
        return [self._worker_task_view(job) for job in jobs]

    def claim_for_worker(self, job_id: str) -> dict[str, Any]:
        """Worker 认领任务：标记 running 并返回任务详情。"""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("任务不存在")
        if job["status"] not in ("queued", "retry"):
            raise ValueError(f"任务状态不允许认领: {job['status']}")

        claimed = self.jobs.mark_running(job_id)
        if not claimed:
            raise ValueError("认领失败")
        return self._worker_task_view(claimed)

    async def resolve_download_for_worker(self, job_id: str) -> dict[str, Any]:
        """为 worker 解析下载链接和必要的请求头。"""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("任务不存在")

        if job["type"] == "local":
            return {"url": "", "headers": {}, "size": int(job.get("size") or 0), "type": "local"}

        provider = job.get("source_provider", "")
        pick_code = job.get("source_pick_code", "")
        user_agent = job.get("source_user_agent") or DEFAULT_UA
        url = job.get("source_url", "")
        headers: dict[str, str] = {}

        if provider == "115-cookie":
            cookie = job.get("source_cookie", "")
            if not cookie:
                raise ValueError("任务缺少 115 Cookie")
            down = await self.pan115.down_url_by_cookie(cookie, pick_code, user_agent)
            url = down["url"]
            headers = down.get("headers") or {}
            headers.setdefault("Cookie", cookie)

        elif provider == "115-open":
            cookie = job.get("source_cookie", "")
            if cookie:
                try:
                    down = await self.pan115.down_url_by_cookie(cookie, pick_code, user_agent)
                    url = down["url"]
                    headers = down.get("headers") or {}
                    headers.setdefault("Cookie", cookie)
                except Exception:
                    access_token = job.get("source_access_token", "")
                    refresh_token = job.get("source_refresh_token", "")
                    if access_token or refresh_token:
                        down = await self.pan115.down_url(access_token, pick_code, user_agent, refresh_token)
                        url = down.get("url", "")
                        headers.update(down.get("headers") or {})
            else:
                access_token = job.get("source_access_token", "")
                refresh_token = job.get("source_refresh_token", "")
                if access_token or refresh_token:
                    down = await self.pan115.down_url(access_token, pick_code, user_agent, refresh_token)
                    url = down.get("url", "")
                    headers.update(down.get("headers") or {})

        elif url:
            # 直接 URL 来源
            stored_headers = job.get("source_headers", "")
            if stored_headers:
                import json as _json
                headers = _json.loads(stored_headers) if isinstance(stored_headers, str) else stored_headers

        if not url:
            raise ValueError("无法解析下载链接，请检查任务来源配置")

        self.jobs.patch(job_id, {"source_url": url, "source_headers": headers})
        return {
            "url": url,
            "headers": {k: str(v) for k, v in headers.items()},
            "size": int(job.get("size") or 0),
            "type": "remote",
        }

    async def create_upload_session_for_worker(self, job_id: str) -> dict[str, Any]:
        """为 worker 创建 SP 上传会话，返回 uploadUrl 和分片参数。"""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("任务不存在")

        profile = self.profile_store.get(job["profile_id"])
        if not profile:
            raise ValueError("SP 配置已不存在")

        remote_dir = job.get("remote_dir", "")
        file_name = job.get("file_name", "")
        total_size = int(job.get("size") or job.get("total") or 0)
        conflict = job.get("conflict_behavior", "fail")

        session = await self.graph.create_upload_session(
            profile, profile["driveId"],
            join_remote_path(remote_dir, file_name),
            conflict,
        )
        chunk_size = self.graph.upload_chunk_size(total_size)

        return {
            "uploadUrl": session["uploadUrl"],
            "totalSize": total_size,
            "chunkSize": chunk_size,
            "remotePath": remote_dir + "/" + file_name if remote_dir else file_name,
            "conflictBehavior": conflict,
        }

    async def complete_for_worker(self, job_id: str) -> dict[str, Any]:
        """Worker 完成任务：记录去重和刷新配额。"""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("任务不存在")

        self.jobs.mark_done(job_id)
        self.jobs.append_log(job_id, "Worker 上传完成")

        try:
            profile = self.profile_store.get(job["profile_id"])
            if profile:
                await self.capacity.refresh_quota(profile)
        except Exception:
            pass

        return {"ok": True, "jobId": job_id, "status": "done"}

    def fail_for_worker(self, job_id: str, error_message: str) -> dict[str, Any]:
        """Worker 上报任务失败。"""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("任务不存在")

        self.jobs.append_log(job_id, error_message)
        self.jobs.mark_failed_or_retry(job_id, ValueError(error_message))
        updated = self.jobs.get(job_id)
        return {"ok": True, "jobId": job_id, "status": updated.get("status", "failed") if updated else "failed"}

    def _worker_task_view(self, job: dict[str, Any]) -> dict[str, Any]:
        """为 worker 构建安全的任务视图（隐藏敏感令牌，暴露必要信息）。"""
        return {
            "id": job.get("id"),
            "type": job.get("type"),
            "status": job.get("status"),
            "fileName": job.get("file_name", ""),
            "remoteDir": job.get("remote_dir", ""),
            "remotePath": job.get("remote_path", ""),
            "size": int(job.get("size") or job.get("total") or 0),
            "sha1": job.get("sha1", ""),
            "conflictBehavior": job.get("conflict_behavior", "fail"),
            "sourceProvider": job.get("source_provider", ""),
            "hasDownloadUrl": bool(job.get("source_url")),
            "profileId": job.get("profile_id", ""),
            "profileName": job.get("profile_name", ""),
            "attempts": int(job.get("attempts") or 0),
            "maxAttempts": int(job.get("max_attempts") or 3),
            "createdAt": job.get("created_at", ""),
            "startedAt": job.get("started_at", ""),
        }
