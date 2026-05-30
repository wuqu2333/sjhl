from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from config.settings import AUTH_BASE_URL, DATA_DIR, GRAPH_BASE_URL
from core.container import AppContainer, get_container


from pathlib import Path
from utils.logging import LOG_FILE, logger


router = APIRouter(tags=["dashboard"])
LOCAL_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def today_utc_range() -> tuple[str, str]:
    now = datetime.now(LOCAL_TZ)
    start = datetime(now.year, now.month, now.day, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


@router.get("/logs")
def get_logs(level: str = "", lines: int = 200):
    """获取应用日志，支持等级过滤"""
    levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
    if not LOG_FILE.exists():
        return {"ok": True, "logs": []}
    raw = LOG_FILE.read_text("utf-8").strip().split("\n")
    result = []
    for line in raw[-lines:]:
        entry = {"text": line, "level": "INFO"}
        for lv in levels:
            if f"[{lv}]" in line:
                entry["level"] = lv
                break
        if level and entry["level"] != level.upper():
            continue
        result.append(entry)
    return {"ok": True, "logs": result, "path": str(LOG_FILE)}


@router.get("/state")
def state(jobsLimit: int = 200, container: AppContainer = Depends(get_container)):
    today_start, today_end = today_utc_range()
    today_uploaded = container.transfer_jobs.completed_stats(today_start, today_end)
    job_limit = min(500, max(20, int(jobsLimit or 200)))
    return {
        "ok": True,
        "app": {
            "name": "SJHL-SP-Manager",
            "dataDir": str(DATA_DIR),
            "graphBaseUrl": GRAPH_BASE_URL,
            "authBaseUrl": AUTH_BASE_URL,
        },
        "profiles": container.profiles.list(),
        "capacityPools": container.capacity_pools.list(),
        "tenantConnections": container.tenants.list(),
        "syncJobs": container.sync_store.list(),
        "catalogScan": container.catalog.get_status(),
        "jobs": container.jobs.list(job_limit),
        "jobStats": {
            "statusCounts": container.jobs.status_counts(),
        },
        "dedupe": {"count": container.dedupe.count(), "latest": container.dedupe.latest(20)},
        "settings": container.app_settings.get(),
        "stats": {
            "todayUploaded": {
                **today_uploaded,
                "startAt": today_start,
                "endAt": today_end,
                "timezone": "Asia/Shanghai",
            }
        },
    }
