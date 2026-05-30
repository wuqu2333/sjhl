from __future__ import annotations

from typing import Any
from urllib.parse import quote


AUTO_PROFILE_ID = "__auto_capacity_pool__"
DEFAULT_CAPACITY_POOL_ID = "default"
POOL_PROFILE_PREFIX = "__capacity_pool__:"


def capacity_pool_profile_id(pool_id: str) -> str:
    pool = str(pool_id or "").strip() or DEFAULT_CAPACITY_POOL_ID
    if pool == DEFAULT_CAPACITY_POOL_ID:
        return AUTO_PROFILE_ID
    return f"{POOL_PROFILE_PREFIX}{pool}"


def is_capacity_pool_profile_id(profile_id: str) -> bool:
    value = str(profile_id or "").strip()
    return value in (AUTO_PROFILE_ID, "auto") or value.startswith(POOL_PROFILE_PREFIX)


def pool_id_from_profile_id(profile_id: str) -> str:
    value = str(profile_id or "").strip()
    if value.startswith(POOL_PROFILE_PREFIX):
        return value.removeprefix(POOL_PROFILE_PREFIX) or DEFAULT_CAPACITY_POOL_ID
    return DEFAULT_CAPACITY_POOL_ID


def remaining(profile: dict[str, Any]) -> int:
    value = int(profile.get("quotaRemaining") or 0)
    if value > 0:
        return value
    total = int(profile.get("quotaTotal") or 0)
    used = int(profile.get("quotaUsed") or 0)
    return max(0, total - used)


class CapacityService:
    def __init__(self, profile_store, graph_client, pool_store=None, reserve_bytes: int = 512 * 1024 * 1024 * 1024):
        self.profile_store = profile_store
        self.graph_client = graph_client
        self.pool_store = pool_store
        self.reserve_bytes = reserve_bytes

    def is_auto(self, profile_id: str) -> bool:
        return is_capacity_pool_profile_id(profile_id)

    def choose_profile(self, size: int = 0, pool_id: str = DEFAULT_CAPACITY_POOL_ID) -> dict[str, Any]:
        """优先选剩余空间最少但够放的 SP，逐个填满"""
        target_pool = str(pool_id or "").strip() or DEFAULT_CAPACITY_POOL_ID
        if self.pool_store and not self.pool_store.get(target_pool):
            raise ValueError(f"容量池不存在：{target_pool}")
        profiles = [
            item
            for item in self.profile_store.list(True)
            if item.get("capacityEnabled", True) and item.get("driveId")
            and (item.get("capacityPoolId") or DEFAULT_CAPACITY_POOL_ID) == target_pool
            and str(item.get("quotaState") or "").lower() not in ("full", "deleted")
        ]
        if not profiles:
            pool_name = target_pool
            if self.pool_store:
                pool = self.pool_store.get(target_pool)
                pool_name = (pool or {}).get("name") or target_pool
            raise ValueError(f"容量池「{pool_name}」中没有可用 SP，请先加入可用文档库")
        # 按剩余空间从小到大排序：优先用快要满的 SP
        ranked = sorted(profiles, key=remaining)
        for profile in ranked:
            free = remaining(profile)
            if free == 0 or free >= int(size or 0) + self.reserve_bytes:
                return profile
        # 都不够放就用剩余最多的
        return sorted(profiles, key=remaining, reverse=True)[0]

    async def refresh_quota(self, profile: dict[str, Any]) -> None:
        if not profile.get("driveId"):
            return
        await self.calculate_usage(profile)

    async def calculate_usage(self, profile: dict[str, Any]) -> dict[str, Any]:
        if not profile.get("driveId"):
            return {}
        files = await self.graph_client.list_remote_tree(profile, profile.get("rootPath", "").strip("/"))
        used = sum(int(f.get("size") or 0) for f in files)
        max_total = 25 * 1024 * 1024 * 1024 * 1024  # SP 上限 25TB
        quota = {
            "total": max_total,
            "used": used,
            "remaining": max(0, max_total - used),
            "state": "full" if used >= max_total else "normal",
        }
        self.profile_store.update_quota(profile["id"], quota)
        return {"fileCount": len(files), **quota}
