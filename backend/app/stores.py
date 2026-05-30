from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import AUTH_BASE_URL, DATA_DIR, GRAPH_BASE_URL, resolve_graph_region
from .json_store import JsonStore
from .pan115 import DEFAULT_UA
from .utils import clean


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEPRECATED_AUTH_FIELDS = {
    "tokenUrl",
    "oauthTokenStyle",
    "openListDriver",
    "openListApiBase",
    "openListServerUse",
}
DEFAULT_CAPACITY_POOL_ID = "default"


def strip_deprecated_auth_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in DEPRECATED_AUTH_FIELDS}


def public_secret(record: dict[str, Any]) -> dict[str, Any]:
    item = strip_deprecated_auth_fields(dict(record))
    item["hasClientSecret"] = bool(item.get("clientSecret"))
    item["hasRefreshToken"] = bool(item.get("refreshToken"))
    item.pop("clientSecret", None)
    item.pop("refreshToken", None)
    return item


def normalize_profile_record(record: dict[str, Any]) -> dict[str, Any]:
    item = dict(record)
    item["capacityPoolId"] = clean(item.get("capacityPoolId")) or DEFAULT_CAPACITY_POOL_ID
    return item


class CapacityPoolStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.store = JsonStore(
            data_dir / "capacity-pools.json",
            {
                "version": 1,
                "pools": [
                    {
                        "id": DEFAULT_CAPACITY_POOL_ID,
                        "name": "默认容量池",
                        "createdAt": now_iso(),
                        "updatedAt": now_iso(),
                    }
                ],
            },
        )

    def _default_pool(self) -> dict[str, Any]:
        return {
            "id": DEFAULT_CAPACITY_POOL_ID,
            "name": "默认容量池",
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }

    def list(self) -> list[dict[str, Any]]:
        pools = [dict(item) for item in self.store.read().get("pools", [])]
        if not any(item.get("id") == DEFAULT_CAPACITY_POOL_ID for item in pools):
            pools.insert(0, self._default_pool())
        return pools

    def get(self, pool_id: str) -> dict[str, Any] | None:
        target = clean(pool_id) or DEFAULT_CAPACITY_POOL_ID
        return next((item for item in self.list() if item.get("id") == target), None)

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        pool_id = clean(data.get("id")) or str(uuid4())
        name = clean(data.get("name")) or "未命名容量池"
        existing = self.get(pool_id)
        pool = {
            "id": pool_id,
            "name": name,
            "createdAt": (existing or {}).get("createdAt") or now_iso(),
            "updatedAt": now_iso(),
        }

        def update(value: dict[str, Any]) -> dict[str, Any]:
            pools = [dict(item) for item in value.get("pools", [])]
            if not any(item.get("id") == DEFAULT_CAPACITY_POOL_ID for item in pools):
                pools.insert(0, self._default_pool())
            index = next((i for i, item in enumerate(pools) if item.get("id") == pool_id), -1)
            if index >= 0:
                pools[index] = pool
            else:
                pools.append(pool)
            return {"version": 1, "pools": pools}

        self.store.update(update)
        return pool

    def remove(self, pool_id: str) -> None:
        target = clean(pool_id)
        if target == DEFAULT_CAPACITY_POOL_ID:
            raise ValueError("默认容量池不能删除")
        self.store.update(
            lambda value: {
                "version": 1,
                "pools": [item for item in value.get("pools", []) if item.get("id") != target],
            }
        )


class ProfileStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.store = JsonStore(data_dir / "profiles.json", {"version": 1, "profiles": []})

    def list(self, include_secrets: bool = False) -> list[dict[str, Any]]:
        profiles = [normalize_profile_record(profile) for profile in self.store.read().get("profiles", [])]
        return profiles if include_secrets else [public_secret(profile) for profile in profiles]

    def get(self, profile_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list(True) if item.get("id") == profile_id), None)

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = self.get(clean(data.get("id"))) if data.get("id") else None
        created_at = existing.get("createdAt") if existing else now_iso()
        region = clean(data.get("region") or (existing or {}).get("region") or "cn")
        defaults = resolve_graph_region(region)
        auth_mode = clean(
            data.get("authMode")
            or (existing or {}).get("authMode")
            or ("refresh_token" if data.get("refreshToken") else "client_credentials")
        )
        profile = {
            **(existing or {}),
            "id": clean(data.get("id")) or str(uuid4()),
            "name": clean(data.get("name")) or "未命名 SP",
            "authMode": auth_mode,
            "region": region,
            "tenantId": clean(data.get("tenantId")) or "common",
            "clientId": clean(data.get("clientId")),
            "clientSecret": clean(data.get("clientSecret")) or (existing or {}).get("clientSecret", ""),
            "redirectUri": clean(data.get("redirectUri")) or "http://localhost",
            "refreshToken": clean(data.get("refreshToken")) or (existing or {}).get("refreshToken", ""),
            "scopes": clean(data.get("scopes")) or (existing or {}).get("scopes", ""),
            "graphBaseUrl": clean(data.get("graphBaseUrl")) or defaults["graphBaseUrl"] or GRAPH_BASE_URL,
            "authBaseUrl": clean(data.get("authBaseUrl")) or defaults["authBaseUrl"] or AUTH_BASE_URL,
            "driveId": clean(data.get("driveId")),
            "siteId": clean(data.get("siteId")),
            "siteHostname": clean(data.get("siteHostname")),
            "sitePath": clean(data.get("sitePath")),
            "libraryName": clean(data.get("libraryName")),
            "rootPath": clean(data.get("rootPath")),
            "sourceConnectionId": clean(data.get("sourceConnectionId")),
            "autoManaged": bool(data.get("autoManaged", False)),
            "capacityEnabled": bool(data.get("capacityEnabled", (existing or {}).get("capacityEnabled", True))),
            "capacityPoolId": clean(data.get("capacityPoolId")) or (existing or {}).get("capacityPoolId") or DEFAULT_CAPACITY_POOL_ID,
            "quotaTotal": int(data.get("quotaTotal") or 0),
            "quotaUsed": int(data.get("quotaUsed") or 0),
            "quotaRemaining": int(data.get("quotaRemaining") or 0),
            "quotaState": clean(data.get("quotaState")),
            "lastQuotaAt": clean(data.get("lastQuotaAt")),
            "notes": clean(data.get("notes")),
            "createdAt": created_at,
            "updatedAt": now_iso(),
        }
        if not profile["tenantId"] or not profile["clientId"]:
            raise ValueError("tenantId 和 clientId 必须填写")
        if profile["authMode"] == "client_credentials" and not profile["clientSecret"]:
            raise ValueError("应用权限模式必须填写 clientSecret")
        if profile["authMode"] == "refresh_token" and not profile["refreshToken"]:
            raise ValueError("Refresh Token 模式必须填写 refreshToken")
        if not profile["driveId"] and not profile["siteId"] and not (profile["siteHostname"] and profile["sitePath"]):
            raise ValueError("必须填写 driveId、siteId，或 siteHostname + sitePath")

        def update(value: dict[str, Any]) -> dict[str, Any]:
            profiles = value.get("profiles", [])
            index = next((i for i, item in enumerate(profiles) if item.get("id") == profile["id"]), -1)
            if index >= 0:
                profiles[index] = profile
            else:
                profiles.append(profile)
            return {"version": 1, "profiles": profiles}

        self.store.update(update)
        return public_secret(profile)

    def remove(self, profile_id: str) -> None:
        self.store.update(
            lambda value: {
                "version": 1,
                "profiles": [item for item in value.get("profiles", []) if item.get("id") != profile_id],
            }
        )

    def set_capacity_enabled(self, profile_id: str, enabled: bool) -> dict[str, Any]:
        current = self.get(profile_id)
        if not current:
            raise ValueError("SP 配置不存在")
        next_profile = {
            **current,
            "capacityEnabled": bool(enabled),
            "capacityPoolId": current.get("capacityPoolId") or DEFAULT_CAPACITY_POOL_ID,
            "updatedAt": now_iso(),
        }
        self.store.update(
            lambda value: {
                "version": 1,
                "profiles": [
                    next_profile if item.get("id") == profile_id else item
                    for item in value.get("profiles", [])
                ],
            }
        )
        return public_secret(next_profile)

    def set_capacity_pool(self, profile_id: str, pool_id: str) -> dict[str, Any]:
        current = self.get(profile_id)
        if not current:
            raise ValueError("SP 配置不存在")
        target_pool = clean(pool_id) or DEFAULT_CAPACITY_POOL_ID
        next_profile = {
            **current,
            "capacityEnabled": True,
            "capacityPoolId": target_pool,
            "updatedAt": now_iso(),
        }
        self.store.update(
            lambda value: {
                "version": 1,
                "profiles": [
                    next_profile if item.get("id") == profile_id else item
                    for item in value.get("profiles", [])
                ],
            }
        )
        return public_secret(next_profile)

    def update_refresh_token(self, profile_id: str, refresh_token: str) -> None:
        if not refresh_token:
            return
        self.store.update(
            lambda value: {
                "version": 1,
                "profiles": [
                    {**item, "refreshToken": refresh_token, "updatedAt": now_iso()}
                    if item.get("id") == profile_id
                    else item
                    for item in value.get("profiles", [])
                ],
            }
        )

    def update_quota(self, profile_id: str, quota: dict[str, Any]) -> None:
        self.store.update(
            lambda value: {
                "version": 1,
                "profiles": [
                    {
                        **item,
                        "quotaTotal": int(quota.get("total") or quota.get("quotaTotal") or 0),
                        "quotaUsed": int(quota.get("used") or quota.get("quotaUsed") or 0),
                        "quotaRemaining": int(quota.get("remaining") or quota.get("quotaRemaining") or 0),
                        "quotaState": clean(quota.get("state") or quota.get("quotaState")),
                        "lastQuotaAt": now_iso(),
                        "updatedAt": now_iso(),
                    }
                    if item.get("id") == profile_id
                    else item
                    for item in value.get("profiles", [])
                ],
            }
        )


class TenantStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.store = JsonStore(data_dir / "tenant-connections.json", {"version": 1, "connections": []})

    def list(self, include_secrets: bool = False) -> list[dict[str, Any]]:
        connections = self.store.read().get("connections", [])
        return connections if include_secrets else [public_secret(item) for item in connections]

    def get(self, connection_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list(True) if item.get("id") == connection_id), None)

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = self.get(clean(data.get("id"))) if data.get("id") else None
        region = clean(data.get("region") or (existing or {}).get("region") or "cn")
        defaults = resolve_graph_region(region)
        connection = {
            "id": clean(data.get("id")) or str(uuid4()),
            "name": clean(data.get("name")) or (existing or {}).get("name") or "Vianet tenant",
            "authMode": clean(data.get("authMode") or (existing or {}).get("authMode") or "client_credentials"),
            "region": region,
            "tenantId": clean(data.get("tenantId")) or (existing or {}).get("tenantId") or "common",
            "clientId": clean(data.get("clientId")) or (existing or {}).get("clientId"),
            "clientSecret": clean(data.get("clientSecret")) or (existing or {}).get("clientSecret", ""),
            "redirectUri": clean(data.get("redirectUri")) or (existing or {}).get("redirectUri") or "http://localhost",
            "refreshToken": clean(data.get("refreshToken")) or (existing or {}).get("refreshToken", ""),
            "scopes": clean(data.get("scopes")) or (existing or {}).get("scopes", ""),
            "graphBaseUrl": clean(data.get("graphBaseUrl")) or (existing or {}).get("graphBaseUrl") or defaults["graphBaseUrl"],
            "authBaseUrl": clean(data.get("authBaseUrl")) or (existing or {}).get("authBaseUrl") or defaults["authBaseUrl"],
            "defaultRootPath": clean(data.get("defaultRootPath")) or (existing or {}).get("defaultRootPath"),
            "importDocumentsOnly": bool(data.get("importDocumentsOnly", (existing or {}).get("importDocumentsOnly", True))),
            "createdAt": (existing or {}).get("createdAt", now_iso()),
            "updatedAt": now_iso(),
        }
        connection = strip_deprecated_auth_fields(connection)
        if not connection["tenantId"] or not connection["clientId"]:
            raise ValueError("租户连接必须填写 tenantId 和 clientId")
        if connection["authMode"] == "client_credentials" and not connection["clientSecret"]:
            raise ValueError("应用权限模式必须填写 clientSecret")
        if connection["authMode"] == "refresh_token" and not connection["refreshToken"]:
            raise ValueError("Refresh Token 模式必须填写 refreshToken")

        def update(value: dict[str, Any]) -> dict[str, Any]:
            items = value.get("connections", [])
            index = next((i for i, item in enumerate(items) if item.get("id") == connection["id"]), -1)
            if index >= 0:
                items[index] = connection
            else:
                items.append(connection)
            return {"version": 1, "connections": items}

        self.store.update(update)
        return public_secret(connection)

    def remove(self, connection_id: str) -> None:
        self.store.update(
            lambda value: {
                "version": 1,
                "connections": [item for item in value.get("connections", []) if item.get("id") != connection_id],
            }
        )

    def update_refresh_token(self, connection_id: str, refresh_token: str) -> None:
        if not refresh_token:
            return
        self.store.update(
            lambda value: {
                "version": 1,
                "connections": [
                    {**item, "refreshToken": refresh_token, "updatedAt": now_iso()}
                    if item.get("id") == connection_id
                    else item
                    for item in value.get("connections", [])
                ],
            }
        )


class SyncStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.store = JsonStore(data_dir / "sync-jobs.json", {"version": 1, "jobs": []})

    def list(self, include_secrets: bool = False) -> list[dict[str, Any]]:
        jobs = self.store.read().get("jobs", [])
        if include_secrets:
            return jobs
        return [{**job, "cookie": None, "hasCookie": bool(job.get("cookie"))} for job in jobs]

    def get(self, sync_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list(True) if item.get("id") == sync_id), None)

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = self.get(clean(data.get("id"))) if data.get("id") else None
        job = {
            **(existing or {}),
            "id": clean(data.get("id")) or str(uuid4()),
            "name": clean(data.get("name")) or "同步作业",
            "enabled": bool(data.get("enabled")),
            "sourceType": clean(data.get("sourceType")) or "local",
            "syncMode": clean(data.get("syncMode")) or "add",
            "intervalMinutes": int(data.get("intervalMinutes") or 0),
            "scheduleTime": clean(data.get("scheduleTime")) if "scheduleTime" in data else clean((existing or {}).get("scheduleTime")),
            "profileId": clean(data.get("profileId")),
            "sourcePath": clean(data.get("sourcePath")),
            "sourceCid": clean(data.get("sourceCid")) or "0",
            "cookie": clean(data.get("cookie")) or (existing or {}).get("cookie", ""),
            "pan115AccountId": clean(data.get("pan115AccountId")) or (existing or {}).get("pan115AccountId", ""),
            "userAgent": clean(data.get("userAgent")),
            "targetDir": clean(data.get("targetDir")),
            "recursive": bool(data.get("recursive", True)),
            "dedupeScope": clean(data.get("dedupeScope")) or "global",
            "nextRunAt": "" if any(key in data for key in ("enabled", "intervalMinutes", "scheduleTime")) else (existing or {}).get("nextRunAt", ""),
            "createdAt": (existing or {}).get("createdAt", now_iso()),
            "updatedAt": now_iso(),
        }
        if not job["profileId"]:
            raise ValueError("同步作业必须选择 SP 或自动容量池")
        if job["sourceType"] == "local" and not job["sourcePath"]:
            raise ValueError("本地同步源必须填写源路径")
        if job["sourceType"] == "115-cookie" and not (job.get("cookie") or job.get("pan115AccountId")):
            raise ValueError("115 同步源必须填写 Cookie 或选择 115 账号")

        def update(value: dict[str, Any]) -> dict[str, Any]:
            jobs = value.get("jobs", [])
            index = next((i for i, item in enumerate(jobs) if item.get("id") == job["id"]), -1)
            if index >= 0:
                jobs[index] = job
            else:
                jobs.append(job)
            return {"version": 1, "jobs": jobs}

        self.store.update(update)
        return {**job, "cookie": None, "hasCookie": bool(job.get("cookie"))}

    def remove(self, sync_id: str) -> None:
        self.store.update(
            lambda value: {
                "version": 1,
                "jobs": [item for item in value.get("jobs", []) if item.get("id") != sync_id],
            }
        )

    def append_log(self, sync_id: str, message: str) -> None:
        def update(value: dict[str, Any]) -> dict[str, Any]:
            jobs = value.get("jobs", [])
            for item in jobs:
                if item.get("id") == sync_id:
                    logs = item.get("logs", [])
                    logs.append({"at": now_iso(), "message": message})
                    item["logs"] = logs[-50:]
                    item["updatedAt"] = now_iso()
                    break
            return {"version": 1, "jobs": jobs}
        self.store.update(update)

    def patch(self, sync_id: str, patch_data: dict[str, Any]) -> None:
        self.store.update(
            lambda value: {
                "version": 1,
                "jobs": [
                    {**item, **patch_data, "updatedAt": now_iso()} if item.get("id") == sync_id else item
                    for item in value.get("jobs", [])
                ],
            }
        )

class Pan115AccountStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.store = JsonStore(data_dir / "pan115-accounts.json", {"version": 1, "accounts": []})

    def list_with_secrets(self) -> list[dict[str, Any]]:
        """返回包含 cookie 和 token 的完整账号列表，仅在服务端内部使用"""
        return list(self._all())

    def list(self) -> list[dict[str, Any]]:
        accounts = self.store.read().get("accounts", [])
        return [
            {
                **a,
                "cookie": None,
                "hasCookie": bool(a.get("cookie")),
                "accessToken": None,
                "hasAccessToken": bool(a.get("accessToken")),
                "refreshToken": None,
                "hasRefreshToken": bool(a.get("refreshToken")),
            }
            for a in accounts
        ]

    def get(self, account_id: str) -> dict[str, Any] | None:
        return next((a for a in self._all() if a.get("id") == account_id), None)

    def _all(self) -> list[dict[str, Any]]:
        return self.store.read().get("accounts", [])

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        existing = self.get(clean(data.get("id"))) if data.get("id") else None
        account = {
            **(existing or {}),
            "id": clean(data.get("id")) or str(uuid4()),
            "name": clean(data.get("name")) or "115账号",
            "cookie": clean(data.get("cookie")) or (existing or {}).get("cookie", ""),
            "accessToken": clean(data.get("accessToken")) or (existing or {}).get("accessToken", ""),
            "refreshToken": clean(data.get("refreshToken")) or (existing or {}).get("refreshToken", ""),
            "userAgent": clean(data.get("userAgent")) or DEFAULT_UA,
            "createdAt": (existing or {}).get("createdAt", now_iso()),
            "updatedAt": now_iso(),
        }
        if not account["cookie"] and not account["accessToken"]:
            raise ValueError("至少填写 Cookie 或 Access Token")

        def update(value: dict[str, Any]) -> dict[str, Any]:
            items = value.get("accounts", [])
            idx = next((i for i, item in enumerate(items) if item.get("id") == account["id"]), -1)
            if idx >= 0:
                items[idx] = account
            else:
                items.append(account)
            return {"version": 1, "accounts": items}

        self.store.update(update)
        public = self.list()
        return next((a for a in public if a.get("id") == account["id"]), account)

    def remove(self, account_id: str) -> None:
        self.store.update(lambda v: {"version": 1, "accounts": [a for a in v.get("accounts", []) if a.get("id") != account_id]})

    def update_open_tokens(self, old_access_token: str, old_refresh_token: str, access_token: str, refresh_token: str) -> int:
        if not access_token and not refresh_token:
            return 0
        updated = 0

        def update(value: dict[str, Any]) -> dict[str, Any]:
            nonlocal updated
            accounts = []
            for item in value.get("accounts", []):
                matched = False
                if old_access_token and item.get("accessToken") == old_access_token:
                    matched = True
                if old_refresh_token and item.get("refreshToken") == old_refresh_token:
                    matched = True
                if matched:
                    updated += 1
                    accounts.append(
                        {
                            **item,
                            "accessToken": access_token,
                            "refreshToken": refresh_token,
                            "updatedAt": now_iso(),
                        }
                    )
                else:
                    accounts.append(item)
            return {"version": 1, "accounts": accounts}

        self.store.update(update)
        return updated


    def patch(self, sync_id: str, patch: dict[str, Any]) -> None:
        self.store.update(
            lambda value: {
                "version": 1,
                "jobs": [
                    {**item, **patch, "updatedAt": now_iso()} if item.get("id") == sync_id else item
                    for item in value.get("jobs", [])
                ],
            }
        )


class AppSettingsStore:
    DEFAULT_OPEN_API_DELAY = {
        "globalMultiplier": 1.0,
        "globalDelaySeconds": 0.5,
        "listDelaySeconds": 0.5,
        "renameDelaySeconds": 0.5,
        "deleteDelaySeconds": 0.5,
        "mutateDelaySeconds": 0.5,
        "downDelaySeconds": 0.5,
    }
    DEFAULT_COOKIE_API_DELAY = {
        "globalMultiplier": 1.0,
        "globalDelaySeconds": 2.0,
        "listDelaySeconds": 3.0,
        "renameDelaySeconds": 1.0,
        "deleteDelaySeconds": 2.0,
        "mutateDelaySeconds": 1.0,
        "downDelaySeconds": 0.5,
    }

    def __init__(self, data_dir: Path = DATA_DIR):
        self.store = JsonStore(
            data_dir / "app-settings.json",
            {
                "version": 1,
                "settings": {
                    "dailyUploadLimitEnabled": False,
                    "dailyUploadLimitBytes": 0,
                    "transferConcurrency": 4,
                    "downloadDir": "",
                    "minFreeSpaceGb": 2,
                    "workerMode": False,
                    "pan115OpenApiDelay": self.DEFAULT_OPEN_API_DELAY,
                    "pan115CookieApiDelay": self.DEFAULT_COOKIE_API_DELAY,
                },
            },
        )

    @classmethod
    def normalize_pan115_delay(cls, value: dict[str, Any] | None, defaults: dict[str, float]) -> dict[str, float]:
        raw = value or {}

        def number(key: str) -> float:
            try:
                parsed = float(raw.get(key, defaults[key]))
            except (TypeError, ValueError):
                parsed = float(defaults[key])
            return max(0.0, parsed)

        return {key: number(key) for key in defaults}

    def get(self) -> dict[str, Any]:
        raw = self.store.read().get("settings", {})
        return {
            "dailyUploadLimitEnabled": bool(raw.get("dailyUploadLimitEnabled", False)),
            "dailyUploadLimitBytes": max(0, int(raw.get("dailyUploadLimitBytes") or 0)),
            "transferConcurrency": min(16, max(1, int(raw.get("transferConcurrency") or 4))),
            "downloadDir": str(raw.get("downloadDir") or ""),
            "minFreeSpaceGb": max(0, int(raw.get("minFreeSpaceGb") or 2)),
            "workerMode": bool(raw.get("workerMode", False)),
            "pan115OpenApiDelay": self.normalize_pan115_delay(raw.get("pan115OpenApiDelay"), self.DEFAULT_OPEN_API_DELAY),
            "pan115CookieApiDelay": self.normalize_pan115_delay(raw.get("pan115CookieApiDelay"), self.DEFAULT_COOKIE_API_DELAY),
        }

    def update(self, data: dict[str, Any]) -> dict[str, Any]:
        current = self.get()
        limit_value = data["dailyUploadLimitBytes"] if "dailyUploadLimitBytes" in data else current["dailyUploadLimitBytes"]
        next_settings = {
            **current,
            "dailyUploadLimitEnabled": bool(data.get("dailyUploadLimitEnabled", current["dailyUploadLimitEnabled"])),
            "dailyUploadLimitBytes": max(0, int(limit_value or 0)),
            "transferConcurrency": min(16, max(1, int(data.get("transferConcurrency", current["transferConcurrency"]) or 4))),
            "downloadDir": str(data.get("downloadDir", current["downloadDir"])),
            "minFreeSpaceGb": max(0, int(data.get("minFreeSpaceGb", current["minFreeSpaceGb"]) or 2)),
            "workerMode": bool(data.get("workerMode", current["workerMode"])),
            "pan115OpenApiDelay": self.normalize_pan115_delay(
                data.get("pan115OpenApiDelay") if "pan115OpenApiDelay" in data else current["pan115OpenApiDelay"],
                self.DEFAULT_OPEN_API_DELAY,
            ),
            "pan115CookieApiDelay": self.normalize_pan115_delay(
                data.get("pan115CookieApiDelay") if "pan115CookieApiDelay" in data else current["pan115CookieApiDelay"],
                self.DEFAULT_COOKIE_API_DELAY,
            ),
        }
        self.store.update(lambda value: {"version": 1, "settings": next_settings})
        return next_settings
