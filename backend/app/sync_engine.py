from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from .capacity import is_capacity_pool_profile_id
from .pan115 import DEFAULT_UA
from .utils import collect_local_files, normalize_remote_dir


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


LOCAL_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def next_run_at(interval_minutes: int) -> str:
    interval = int(interval_minutes or 0)
    if interval <= 0:
        return ""
    return (datetime.now(timezone.utc) + timedelta(minutes=interval)).isoformat()


def is_future_iso(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > datetime.now(timezone.utc)


def parse_iso_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_schedule_time(value: str) -> time | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        hour, minute = raw.split(":", 1)
        return time(hour=int(hour), minute=int(minute))
    except Exception:
        return None


def local_date_from_iso(value: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(LOCAL_TZ).date()


def next_schedule_run_at(schedule_time: str) -> str:
    parsed = parse_schedule_time(schedule_time)
    if not parsed:
        return ""
    now = datetime.now(LOCAL_TZ)
    today = datetime.combine(now.date(), parsed, tzinfo=LOCAL_TZ)
    target = today if today > now else today + timedelta(days=1)
    return target.astimezone(timezone.utc).isoformat()


def next_due_at(interval_minutes: int, schedule_time: str) -> str:
    candidates = [parse_iso_utc(item) for item in [next_run_at(interval_minutes), next_schedule_run_at(schedule_time)]]
    candidates = [item for item in candidates if item is not None]
    if not candidates:
        return ""
    return min(candidates).isoformat()


def should_run_scheduled(job: dict[str, Any]) -> bool:
    parsed = parse_schedule_time(job.get("scheduleTime") or "")
    if not parsed:
        return False
    next_at = job.get("nextRunAt") or ""
    if not next_at or is_future_iso(next_at):
        return False
    now = datetime.now(LOCAL_TZ)
    return local_date_from_iso(job.get("lastRunAt") or "") != now.date()


def parent_remote_dir(remote_path: str) -> str:
    parts = [part for part in str(remote_path or "").replace("\\", "/").split("/") if part]
    if parts:
        parts.pop()
    return "/".join(parts)


def with_root_path(profile: dict[str, Any], target_dir: str) -> str:
    return normalize_remote_dir("/".join(part for part in [profile.get("rootPath"), target_dir] if part))


def local_relative_path(base_local_path: Path, file_path: Path) -> str:
    return file_path.relative_to(base_local_path).as_posix()


def remote_path_for_source(target_root: str, relative_path: str) -> dict[str, str]:
    remote_path = normalize_remote_dir("/".join(part for part in [target_root, relative_path] if part))
    return {"remotePath": remote_path, "remoteDir": parent_remote_dir(remote_path)}


def dest_map_by_path(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("remotePath") or "").lower(): item for item in files if item.get("remotePath")}


def should_upload(source: dict[str, Any], destination: dict[str, Any] | None, sync_mode: str) -> bool:
    if not destination:
        return True
    if sync_mode != "full":
        return False
    source_size = int(source.get("size") or 0)
    dest_size = int(destination.get("size") or 0)
    if source_size != dest_size:
        return True
    source_sha1 = str(source.get("sha1") or "").lower()
    dest_sha1 = str(destination.get("sha1") or "").lower()
    if source_sha1 and dest_sha1:
        return source_sha1 != dest_sha1
    source_sha256 = str(source.get("sha256") or "").lower()
    dest_sha256 = str(destination.get("sha256") or "").lower()
    if source_sha256 and dest_sha256:
        return source_sha256 != dest_sha256
    return False


class SyncEngine:
    def __init__(self, sync_store, profile_store, graph_client, pan115_client, job_queue, dedupe_store):
        self.sync_store = sync_store
        self.profile_store = profile_store
        self.graph = graph_client
        self.pan115 = pan115_client
        self.job_queue = job_queue
        self.dedupe = dedupe_store
        self.running: set[str] = set()

    async def tick(self) -> None:
        for job in self.sync_store.list(True):
            if not job.get("enabled"):
                continue
            if job.get("id") in self.running:
                continue
            interval = int(job.get("intervalMinutes") or 0)
            interval_due = False
            if interval > 0:
                next_at = job.get("nextRunAt") or ""
                interval_due = not is_future_iso(next_at)
            if interval <= 0 and job.get("scheduleTime") and not job.get("nextRunAt"):
                self.sync_store.patch(job["id"], {"nextRunAt": next_schedule_run_at(job.get("scheduleTime") or "")})
                continue
            scheduled_due = should_run_scheduled(job)
            if not interval_due and not scheduled_due:
                continue
            asyncio.create_task(self.run(job["id"]))

    def _log(self, sync_id: str, msg: str) -> None:
        from utils.logging import logger
        logger.info(f"Sync[{sync_id[:8]}]: {msg}")
        self.sync_store.append_log(sync_id, msg)

    async def run(self, sync_id: str) -> dict[str, Any]:
        if sync_id in self.running:
            raise ValueError("同步作业正在运行")
        self.running.add(sync_id)
        self._log(sync_id, "开始执行")
        self.sync_store.patch(sync_id, {"lastStatus": "running", "lastRunAt": now_iso(), "lastError": ""})
        job: dict[str, Any] | None = None
        try:
            job = self.sync_store.get(sync_id)
            if not job:
                raise ValueError("同步作业不存在")
            auto_profile = is_capacity_pool_profile_id(job.get("profileId"))
            profile = None if auto_profile else self.profile_store.get(job.get("profileId"))
            if not profile and not auto_profile:
                raise ValueError("SP 配置不存在")
            source_type = job.get("sourceType")
            self._log(sync_id, f"源类型: {source_type}, 源: {job.get('sourcePath') or job.get('sourceCid')}")
            summary = await (self.run_local(job, profile) if source_type == "local" else self.run_115_cookie(job, profile))
            self._log(sync_id, f"完成: 扫描 {summary.get('scanned',0)} 个, 入队 {summary.get('queued',0)} 个, 跳过 {summary.get('skipped',0)} 个")
            next_at = next_due_at(job.get("intervalMinutes") or 0, job.get("scheduleTime") or "")
            self.sync_store.patch(sync_id, {
                "lastStatus": "done", "lastSummary": summary,
                "nextRunAt": next_at,
            })
            return summary
        except Exception as error:
            self._log(sync_id, f"失败: {error}")
            next_at = ""
            if job:
                next_at = next_due_at(job.get("intervalMinutes") or 0, job.get("scheduleTime") or "")
            self.sync_store.patch(sync_id, {"lastStatus": "failed", "lastError": str(error), "nextRunAt": next_at})
            raise
        finally:
            self.running.discard(sync_id)

    async def destination_map(self, profile: dict[str, Any] | None, target_dir: str) -> dict[str, Any]:
        if not profile:
            return {"targetRoot": normalize_remote_dir(target_dir), "map": {}}
        target_root = with_root_path(profile, target_dir or "")
        files = await self.graph.list_remote_tree(profile, target_root)
        return {"targetRoot": target_root, "map": dest_map_by_path(files)}

    async def run_local(self, job: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
        base_local_path, files = collect_local_files(job.get("sourcePath"), bool(job.get("recursive", True)))
        destination = await self.destination_map(profile, job.get("targetDir") or "")
        queued = 0
        skipped = 0
        for file_path in files:
            stat = file_path.stat()
            relative_path = local_relative_path(base_local_path, file_path)
            planned = remote_path_for_source(destination["targetRoot"], relative_path)
            upload_target = remote_path_for_source(job.get("targetDir") or "", relative_path)
            existing = destination["map"].get(planned["remotePath"].lower())
            if not should_upload({"size": stat.st_size}, existing, job.get("syncMode") or "add"):
                skipped += 1
                continue
            created = self.job_queue.enqueue_local(
                {
                    "profileId": job.get("profileId"),
                    "localPath": str(file_path),
                    "remoteDir": parent_remote_dir(upload_target["remotePath"]),
                    "recursive": False,
                    "dedupeScope": job.get("dedupeScope"),
                    "conflictBehavior": "replace" if job.get("syncMode") == "full" and existing else "replace",
                }
            )
            if any(item.get("status") == "queued" for item in created):
                queued += 1
            else:
                skipped += 1
        return {
            "sourceType": job.get("sourceType"),
            "syncMode": job.get("syncMode"),
            "scanned": len(files),
            "queued": queued,
            "skipped": skipped,
        }

    async def run_115_cookie(self, job: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
        user_agent = job.get("userAgent") or DEFAULT_UA
        account = None
        if job.get("pan115AccountId") and hasattr(self, "pan115_accounts"):
            account = self.pan115_accounts.get(job["pan115AccountId"])
        scan_account = dict(account or {})
        if job.get("cookie"):
            scan_account["cookie"] = job.get("cookie")
        if not scan_account.get("accessToken") and not scan_account.get("cookie"):
            raise ValueError("115 账号未配置有效认证，请先在设置中获取 Token 或保存 Cookie")
        scan_result = await self.pan115.list_files_auto(
            scan_account, job.get("sourceCid") or "0", user_agent, bool(job.get("recursive", True)),
        )
        source_files = scan_result.get("files") or []
        source_provider = scan_result.get("provider") or ("115-open" if scan_account.get("accessToken") else "115-cookie")
        target_dir = job.get("targetDir") or ""
        destination = await self.destination_map(profile, target_dir)
        queued = 0
        skipped = 0
        for source in source_files:
            planned = remote_path_for_source(destination["targetRoot"], source.get("relativePath") or source.get("name") or "")
            upload_target = remote_path_for_source(target_dir, source.get("relativePath") or source.get("name") or "")
            existing = destination["map"].get(planned["remotePath"].lower())
            if not should_upload(source, existing, job.get("syncMode") or "add"):
                skipped += 1; continue
            if not source.get("pickCode"):
                skipped += 1; continue
            file_name = (source.get("relativePath") or source.get("name") or "").split("/")[-1]
            if file_name and source.get("size") and self.dedupe.find(file_name, int(source["size"])):
                skipped += 1; continue
            enqueue_data = {
                "profileId": job.get("profileId"),
                "sourceUrl": "",
                "sourceHeaders": {},
                "sourceProvider": source_provider,
                "sourcePickCode": source["pickCode"],
                "sourceUserAgent": user_agent,
                "fileName": file_name,
                "remoteDir": parent_remote_dir(upload_target["remotePath"]),
                "size": source.get("size"),
                "sha1": source.get("sha1"),
                "dedupeScope": job.get("dedupeScope"),
                "conflictBehavior": "replace",
            }
            if source_provider == "115-open":
                enqueue_data["sourceAccessToken"] = scan_result.get("accessToken") or scan_account.get("accessToken") or ""
                enqueue_data["sourceRefreshToken"] = scan_result.get("refreshToken") or scan_account.get("refreshToken") or ""
                if scan_account.get("cookie"):
                    enqueue_data["sourceCookie"] = scan_account.get("cookie") or ""
            else:
                enqueue_data["sourceCookie"] = scan_result.get("cookie") or scan_account.get("cookie") or ""
            self.job_queue.enqueue_remote_url(enqueue_data)
            queued += 1
        return {
            "sourceType": job.get("sourceType"), "syncMode": job.get("syncMode"),
            "scanned": len(source_files), "queued": queued, "skipped": skipped,
        }
