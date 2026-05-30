from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote, unquote, urlparse


def profile_id_for_drive(connection_id: str, drive_id: str) -> str:
    return "drive-" + hashlib.sha1(f"{connection_id}:{drive_id}".encode()).hexdigest()[:20]


def profile_from_drive(connection: dict[str, Any], drive: dict[str, Any], root_path: str = "") -> dict[str, Any]:
    return {
        "id": profile_id_for_drive(connection["id"], drive["driveId"]),
        "name": " / ".join(part for part in [drive.get("siteName"), drive.get("driveName")] if part),
        "authMode": connection.get("authMode"),
        "region": connection.get("region"),
        "tenantId": connection.get("tenantId"),
        "clientId": connection.get("clientId"),
        "clientSecret": connection.get("clientSecret"),
        "redirectUri": connection.get("redirectUri"),
        "refreshToken": connection.get("refreshToken"),
        "scopes": connection.get("scopes"),
        "graphBaseUrl": connection.get("graphBaseUrl"),
        "authBaseUrl": connection.get("authBaseUrl"),
        "driveId": drive.get("driveId"),
        "siteId": drive.get("siteId"),
        "libraryName": drive.get("driveName"),
        "rootPath": root_path or connection.get("defaultRootPath") or "",
        "sourceConnectionId": connection.get("id"),
        "autoManaged": True,
        "quotaTotal": drive.get("quotaTotal") or 0,
        "quotaUsed": drive.get("quotaUsed") or 0,
        "quotaRemaining": drive.get("quotaRemaining") or 0,
        "quotaState": drive.get("quotaState") or "",
        "notes": drive.get("webUrl") or drive.get("siteWebUrl") or "",
    }


class TenantDiscoveryService:
    def __init__(self, tenant_store, profile_store, graph_client):
        self.tenant_store = tenant_store
        self.profile_store = profile_store
        self.graph = graph_client

    async def discover(self, connection_id: str, options: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        options = options or {}
        connection = self.tenant_store.get(connection_id)
        if not connection:
            raise ValueError("未找到租户连接")
        return await self.graph.discover_sharepoint_drives(
            connection,
            search=options.get("search") or "*",
            documents_only=bool(options.get("documentsOnly", connection.get("importDocumentsOnly", True))),
        )

    async def import_discovered(self, connection_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        connection = self.tenant_store.get(connection_id)
        if not connection:
            raise ValueError("未找到租户连接")
        drives = await self.discover(connection_id, options)
        profiles = [
            self.profile_store.upsert(profile_from_drive(connection, drive, options.get("rootPath") or connection.get("defaultRootPath") or ""))
            for drive in drives
        ]
        return {"count": len(profiles), "profiles": profiles}

    async def mount_sharepoint_site(self, connection_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        connection = self.tenant_store.get(connection_id)
        if not connection:
            raise ValueError("未找到租户连接")
        site_url = str(options.get("siteUrl") or "").strip()
        if not site_url:
            raise ValueError("必须填写 SharePoint 站点 URL")
        site_api_path = sharepoint_site_api_path(site_url)
        site = await self.graph.request(connection, "GET", site_api_path)
        drive_items: list[dict[str, Any]] = []
        next_drives = f"/sites/{quote(site['id'], safe='')}/drives"
        while next_drives:
            drives = await self.graph.request(connection, "GET", next_drives)
            drive_items.extend(drives.get("value") or [])
            next_drives = drives.get("@odata.nextLink") or ""
        documents_only = bool(options.get("documentsOnly", connection.get("importDocumentsOnly", True)))
        library_name = str(options.get("libraryName") or "").strip().lower()
        matched_drives = []
        for drive in drive_items:
            drive_type = str(drive.get("driveType") or "").lower()
            drive_name = str(drive.get("name") or "")
            if documents_only and drive_type and drive_type not in ("documentlibrary", "business"):
                continue
            if library_name and drive_name.lower() != library_name:
                continue
            quota = drive.get("quota") or {}
            matched_drives.append(
                {
                    "siteId": site.get("id"),
                    "siteName": site.get("displayName") or site.get("name") or "",
                    "siteWebUrl": site.get("webUrl") or site_url,
                    "driveId": drive.get("id"),
                    "driveName": drive_name,
                    "driveType": drive.get("driveType") or "",
                    "webUrl": drive.get("webUrl") or "",
                    "quotaTotal": int(quota.get("total") or 0),
                    "quotaUsed": int(quota.get("used") or 0),
                    "quotaRemaining": int(quota.get("remaining") or 0),
                    "quotaState": quota.get("state") or "",
                }
            )
        if library_name and not matched_drives:
            raise ValueError(f"站点中未找到文档库: {options.get('libraryName')}")
        profiles = [
            self.profile_store.upsert(
                profile_from_drive(connection, drive, options.get("rootPath") or connection.get("defaultRootPath") or "")
            )
            for drive in matched_drives
        ]
        return {"count": len(profiles), "site": site, "drives": matched_drives, "profiles": profiles}


def sharepoint_site_api_path(site_url: str) -> str:
    parsed = urlparse(site_url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("SharePoint 站点 URL 必须是完整地址，例如 https://tenant.sharepoint.cn/sites/media")
    host = parsed.netloc.lower()
    site_path = unquote(parsed.path or "/").rstrip("/")
    if not site_path:
        site_path = "/"
    if site_path == "/":
        return f"/sites/{quote(host, safe='.')}"
    return f"/sites/{quote(host, safe='.')}:/{quote(site_path.strip('/'), safe='/')}"
