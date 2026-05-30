"""
SP → OpenList 自动挂载管理器
============================
通过 Microsoft Graph API 自动发现 SharePoint 站点和文档库，
一键调用 OpenList API 挂载存储。提供 Web 管理界面。

使用方式:
  - OpenList 地址 + API Key  →  连接 OpenList
  - SP 租户凭证             →  发现站点/文档库
  - 选中文档库 → 调用 OpenList API 挂载
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data"
STATIC_DIR = Path(__file__).resolve().parent / "static"
HOST = "0.0.0.0"
PORT = 17653

SETTINGS_FILE = DATA_DIR / "settings.json"
CONNECTIONS_FILE = DATA_DIR / "connections.json"
MOUNTS_FILE = DATA_DIR / "mounts.json"

# Microsoft Graph 区域
GRAPH_REGIONS = {
    "cn": {
        "label": "世纪互联 (中国)",
        "graphBaseUrl": "https://microsoftgraph.chinacloudapi.cn/v1.0",
        "authBaseUrl": "https://login.partner.microsoftonline.cn",
    },
    "global": {
        "label": "国际版 (Global)",
        "graphBaseUrl": "https://graph.microsoft.com/v1.0",
        "authBaseUrl": "https://login.microsoftonline.com",
    },
}

EXCLUDED_SITE_NAMES = {"team site", "communication site"}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def mask_secret(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 6:
        return "*" * len(s)
    return s[:3] + "*" * (len(s) - 6) + s[-3:]


def slugify(text: str) -> str:
    """将文本转为安全的路径片段。"""
    text = re.sub(r"[^\w一-鿿\-]", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_") or "unnamed"


# ---------------------------------------------------------------------------
# OpenList API 客户端
# ---------------------------------------------------------------------------

class OpenListClient:
    """OpenList API 客户端，用于调用 OpenList 的管理接口。"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def list_storage(self) -> list[dict[str, Any]]:
        """列出 OpenList 中已有的存储。"""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/admin/storage/list",
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenList API 错误 [{resp.status_code}]: {resp.text[:500]}")
            data = resp.json()
            return data.get("data", {}).get("content", [])

    async def create_storage(self, mount_path: str, driver: str, addition: dict[str, Any]) -> dict[str, Any]:
        """在 OpenList 中创建存储挂载。"""
        body = {
            "mount_path": mount_path,
            "driver": driver,
            "addition": json.dumps(addition, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/admin/storage/create",
                headers=self._headers(),
                json=body,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenList API 错误 [{resp.status_code}]: {resp.text[:500]}")
            return resp.json()

    async def delete_storage(self, storage_id: int) -> dict[str, Any]:
        """从 OpenList 中删除存储。"""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/admin/storage/delete",
                headers=self._headers(),
                json={"id": storage_id},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenList API 错误 [{resp.status_code}]: {resp.text[:500]}")
            return resp.json()

    async def get_storage(self, storage_id: int) -> dict[str, Any]:
        """获取单个存储信息。"""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/admin/storage/info",
                headers=self._headers(),
                params={"id": storage_id},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenList API 错误 [{resp.status_code}]: {resp.text[:500]}")
            return resp.json()

    async def test(self) -> dict[str, Any]:
        """测试 OpenList 连接。"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base_url}/api/admin/storage/list",
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"连接 OpenList 失败 [{resp.status_code}]: {resp.text[:300]}")
            return resp.json()


# ---------------------------------------------------------------------------
# Microsoft Graph 客户端
# ---------------------------------------------------------------------------

class GraphClient:
    """Microsoft Graph 客户端，用于发现 SharePoint 站点和文档库。"""

    def __init__(self):
        self._token_cache: dict[str, dict[str, Any]] = {}

    def _cache_key(self, conn: dict[str, Any]) -> str:
        return f"{conn.get('region','cn')}:{conn.get('tenantId')}:{conn.get('clientId')}"

    def _graph_base(self, conn: dict[str, Any]) -> str:
        return GRAPH_REGIONS.get(conn.get("region", "cn"), GRAPH_REGIONS["cn"])["graphBaseUrl"]

    def _auth_base(self, conn: dict[str, Any]) -> str:
        return GRAPH_REGIONS.get(conn.get("region", "cn"), GRAPH_REGIONS["cn"])["authBaseUrl"]

    async def _acquire_token(self, conn: dict[str, Any]) -> str:
        cache_key = self._cache_key(conn)
        cached = self._token_cache.get(cache_key)
        if cached and cached.get("expires_at", 0) > time.time() + 60:
            return cached["access_token"]

        graph_origin = self._graph_base(conn).split("/v1.0")[0]
        auth_mode = conn.get("authMode", "client_credentials")
        params: dict[str, str] = {
            "client_id": conn["clientId"],
            "grant_type": "refresh_token" if auth_mode == "refresh_token" else "client_credentials",
            "scope": (
                f"{graph_origin}/.default"
                if auth_mode == "client_credentials"
                else conn.get("scopes", f"{graph_origin}/Files.ReadWrite.All Sites.ReadWrite.All offline_access")
            ),
        }
        if conn.get("clientSecret"):
            params["client_secret"] = conn["clientSecret"]
        if auth_mode == "refresh_token":
            params["refresh_token"] = conn.get("refreshToken", "")
            params["redirect_uri"] = conn.get("redirectUri", "http://localhost")

        token_url = f"{self._auth_base(conn)}/{conn.get('tenantId', 'common')}/oauth2/v2.0/token"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(token_url, data=params)
            if resp.status_code >= 400:
                raise RuntimeError(f"获取 Graph 令牌失败 [{resp.status_code}]: {resp.text[:500]}")
            data = resp.json()
            self._token_cache[cache_key] = {
                "access_token": data["access_token"],
                "expires_at": time.time() + int(data.get("expires_in", 3600)),
            }
            return data["access_token"]

    async def request(self, conn: dict[str, Any], method: str, path: str, json_body: Any = None) -> dict[str, Any]:
        token = await self._acquire_token(conn)
        url = f"{self._graph_base(conn)}{path}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=60) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=json_body)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"不支持的方法: {method}")
            if resp.status_code == 404:
                raise RuntimeError(f"资源未找到: {path}")
            if resp.status_code >= 400:
                raise RuntimeError(f"Graph API 错误 [{resp.status_code}]: {resp.text[:500]}")
            if resp.status_code == 204:
                return {}
            return resp.json()

    async def discover_sites(self, conn: dict[str, Any], search: str = "*") -> list[dict[str, Any]]:
        sites: list[dict[str, Any]] = []
        try:
            result = await self.request(conn, "GET", "/sites/getAllSites")
            for s in result.get("value", []):
                sites.append(s)
        except Exception:
            pass
        if search:
            try:
                result = await self.request(conn, "GET", f"/sites?search={quote(search)}")
                for s in result.get("value", []):
                    if not any(x.get("id") == s.get("id") for x in sites):
                        sites.append(s)
            except Exception:
                pass
        return [s for s in sites if not _is_excluded_site(s)]

    async def discover_drives(self, conn: dict[str, Any], site: dict[str, Any]) -> list[dict[str, Any]]:
        drives: list[dict[str, Any]] = []
        site_id = site.get("id", "")
        next_url = f"/sites/{quote(site_id, safe='')}/drives"
        while next_url:
            result = await self.request(conn, "GET", next_url)
            drives.extend(result.get("value", []))
            next_url = result.get("@odata.nextLink", "")
        return drives

    async def resolve_site_by_url(self, conn: dict[str, Any], site_url: str) -> dict[str, Any]:
        parsed = urlparse(site_url.strip())
        host = parsed.netloc.lower()
        site_path = unquote(parsed.path or "/").rstrip("/") or "/"
        if site_path == "/":
            api_path = f"/sites/{quote(host, safe='.')}"
        else:
            api_path = f"/sites/{quote(host, safe='.')}:/{quote(site_path.strip('/'), safe='/')}"
        return await self.request(conn, "GET", api_path)


def _is_excluded_site(site: dict[str, Any]) -> bool:
    name = str(site.get("displayName") or site.get("name") or "").strip().lower()
    web_url = str(site.get("webUrl") or "").strip()
    parsed = urlparse(web_url)
    path = (parsed.path or "/").rstrip("/").lower() or "/"
    host = parsed.netloc.lower()
    return (
        name in EXCLUDED_SITE_NAMES
        or path in {"", "/", "/search", "/sites/contenttypehub"}
        or "-my.sharepoint." in host
        or "/personal/" in path
    )


# ---------------------------------------------------------------------------
# 数据存取
# ---------------------------------------------------------------------------

def load_settings() -> dict[str, Any]:
    return read_json(
        SETTINGS_FILE,
        {
            "openListUrl": "",
            "openListApiKey": "",
        },
    )


def save_settings(data: dict[str, Any]) -> None:
    write_json(SETTINGS_FILE, data)


def load_connections() -> list[dict[str, Any]]:
    return read_json(CONNECTIONS_FILE, {"connections": []}).get("connections", [])


def save_connections(items: list[dict[str, Any]]) -> None:
    write_json(CONNECTIONS_FILE, {"connections": items})


def load_mounts() -> list[dict[str, Any]]:
    return read_json(MOUNTS_FILE, {"mounts": []}).get("mounts", [])


def save_mounts(items: list[dict[str, Any]]) -> None:
    write_json(MOUNTS_FILE, {"mounts": items})


def _get_connection(conn_id: str) -> dict[str, Any]:
    conn = next((c for c in load_connections() if c.get("id") == conn_id), None)
    if not conn:
        raise AppError(404, "连接不存在")
    return conn


# ---------------------------------------------------------------------------
# OpenList 挂载逻辑
# ---------------------------------------------------------------------------

def build_mount_path(site_name: str, drive_name: str) -> str:
    """生成 OpenList 挂载路径，如 /sharepoint/SiteName_DriveName"""
    return f"/sharepoint/{slugify(site_name)}_{slugify(drive_name)}"


def build_onedrive_addition(connection: dict[str, Any], drive: dict[str, Any], site: dict[str, Any]) -> dict[str, Any]:
    """根据 SP 文档库信息构建 OpenList Onedrive 驱动的 addition 参数。"""
    region = connection.get("region", "cn")
    redirect_uri = "https://api.oplist.org/onedrive/callback"
    return {
        "redirect_uri": redirect_uri,
        "client_id": connection.get("clientId", ""),
        "client_secret": connection.get("clientSecret", ""),
        "refresh_token": connection.get("refreshToken", ""),
        "region": region,
        "site_url": site.get("webUrl", ""),
        "site_id": site.get("id", ""),
        "drive_id": drive.get("id", ""),
        "drive_name": drive.get("name", ""),
        "chunk_size": 5,
        "root_folder_path": "/",
    }


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(title="SP → OpenList 挂载管理器", version="2.0.0")


class AppError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    detail = str(exc)
    code = 500
    if any(kw in detail for kw in ("未找到", "不存在")):
        code = 404
    elif any(kw in detail for kw in ("必须", "必填", "不支持")):
        code = 400
    elif any(kw in detail for kw in ("令牌", "认证", "Unauthorized")):
        code = 401
    return JSONResponse(status_code=code, content={"error": detail})


# --- OpenList 设置 ---

@app.get("/api/settings")
def get_settings():
    s = load_settings()
    return {
        "openListUrl": s.get("openListUrl", ""),
        "openListApiKey": mask_secret(s.get("openListApiKey", "")),
        "hasApiKey": bool(s.get("openListApiKey")),
    }


@app.post("/api/settings")
def update_settings(body: dict[str, Any]):
    s = load_settings()
    if "openListUrl" in body:
        s["openListUrl"] = body["openListUrl"].strip().rstrip("/")
    if "openListApiKey" in body and body["openListApiKey"]:
        s["openListApiKey"] = body["openListApiKey"].strip()
    save_settings(s)
    return {"ok": True}


@app.post("/api/settings/test-openlist")
async def test_openlist():
    s = load_settings()
    if not s.get("openListUrl") or not s.get("openListApiKey"):
        raise AppError(400, "请先填写 OpenList 地址和 API Key")
    client = OpenListClient(s["openListUrl"], s["openListApiKey"])
    result = await client.test()
    return {"ok": True, "storage_count": len(result.get("data", {}).get("content", []))}


# --- SP 连接管理 ---

@app.get("/api/connections")
def list_connections():
    return [mask_connection(c) for c in load_connections()]


@app.post("/api/connections")
def save_connection(body: dict[str, Any]):
    connections = load_connections()
    conn_id = body.get("id") or str(uuid.uuid4())
    idx = next((i for i, c in enumerate(connections) if c.get("id") == conn_id), -1)
    now = now_iso()
    conn = {
        "id": conn_id,
        "name": body.get("name", "未命名连接"),
        "authMode": body.get("authMode", "client_credentials"),
        "region": body.get("region", "cn"),
        "tenantId": body.get("tenantId", "common"),
        "clientId": body.get("clientId", ""),
        "clientSecret": body.get("clientSecret", ""),
        "redirectUri": body.get("redirectUri", "http://localhost"),
        "refreshToken": body.get("refreshToken", ""),
        "scopes": body.get("scopes", ""),
        "createdAt": (connections[idx] if idx >= 0 else {}).get("createdAt", now),
        "updatedAt": now,
    }
    if idx >= 0:
        if not conn["clientSecret"]:
            conn["clientSecret"] = connections[idx].get("clientSecret", "")
        if not conn["refreshToken"]:
            conn["refreshToken"] = connections[idx].get("refreshToken", "")
        connections[idx] = conn
    else:
        connections.append(conn)
    save_connections(connections)
    return mask_connection(conn)


@app.delete("/api/connections/{connection_id}")
def delete_connection(connection_id: str):
    save_connections([c for c in load_connections() if c.get("id") != connection_id])


# --- OAuth 设备代码流 获取 Refresh Token ---



@app.post("/api/connections/{connection_id}/device-code")
async def get_device_code(connection_id: str):
    """发起设备代码流：返回验证 URL 和用户码，用户去 microsoft.com/devicelogin 输入即可。"""
    conn = _get_connection(connection_id)
    region = conn.get("region", "cn")
    defaults = GRAPH_REGIONS.get(region, GRAPH_REGIONS["cn"])
    auth_base = defaults["authBaseUrl"]
    graph_origin = defaults["graphBaseUrl"].split("/v1.0")[0]

    client_id = conn.get("clientId", "")
    scopes = conn.get("scopes", "") or f"{graph_origin}/Files.ReadWrite.All {graph_origin}/Sites.ReadWrite.All offline_access"

    device_code_url = f"{auth_base}/{conn.get('tenantId', 'common')}/oauth2/v2.0/devicecode"
    body = {"client_id": client_id, "scope": scopes}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(device_code_url, data=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"设备代码请求失败 [{resp.status_code}]: {resp.text[:500]}")
        data = resp.json()

    device_code = data["device_code"]
    key = f"devicecode:{connection_id}"
    _device_code_store[key] = {
        "device_code": device_code,
        "client_id": client_id,
        "conn_id": connection_id,
        "expires_at": time.time() + int(data.get("expires_in", 900)),
        "interval": int(data.get("interval", 5)),
    }

    return {
        "verification_uri": data["verification_uri"],
        "user_code": data["user_code"],
        "message": data.get("message", ""),
        "expires_in": data.get("expires_in", 900),
    }


@app.post("/api/connections/{connection_id}/device-code/poll")
async def poll_device_code(connection_id: str):
    """轮询设备代码是否已完成授权。"""
    key = f"devicecode:{connection_id}"
    entry = _device_code_store.get(key)
    if not entry:
        raise AppError(404, "设备代码会话已过期，请重新发起")

    if time.time() > entry["expires_at"]:
        _device_code_store.pop(key, None)
        raise AppError(410, "设备代码已过期，请重新发起")

    region = _get_connection(connection_id).get("region", "cn")
    defaults = GRAPH_REGIONS.get(region, GRAPH_REGIONS["cn"])
    auth_base = defaults["authBaseUrl"]

    token_url = f"{auth_base}/{_get_connection(connection_id).get('tenantId', 'common')}/oauth2/v2.0/token"
    body = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": entry["device_code"],
        "client_id": entry["client_id"],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(token_url, data=body)
        if resp.status_code >= 400:
            data = resp.json()
            error = data.get("error", "")
            error_desc = data.get("error_description", "")
            if error == "authorization_pending":
                return {"status": "pending"}
            elif error == "slow_down":
                entry["interval"] = entry.get("interval", 5) + 5
                _device_code_store[key] = entry
                return {"status": "pending", "slow_down": True}
            elif error == "expired_token":
                _device_code_store.pop(key, None)
                raise AppError(410, "设备代码已过期")
            else:
                raise RuntimeError(f"Token 交换失败: {error} - {error_desc}")
        data = resp.json()

    refresh_token = data.get("refresh_token", "")
    if not refresh_token:
        raise RuntimeError("未获取到 refresh_token，请确认已在 Azure AD 中授予 offline_access 权限")

    _device_code_store.pop(key, None)
    _save_refresh_token(connection_id, refresh_token)
    return {"status": "done"}


@app.delete("/api/connections/{connection_id}/device-code")
def cancel_device_code(connection_id: str):
    """取消设备代码授权。"""
    _device_code_store.pop(f"devicecode:{connection_id}", None)
    return {"ok": True}


def _save_refresh_token(conn_id: str, refresh_token: str) -> None:
    connections = load_connections()
    idx = next((i for i, c in enumerate(connections) if c.get("id") == conn_id), -1)
    if idx >= 0:
        connections[idx]["refreshToken"] = refresh_token
        connections[idx]["authMode"] = "refresh_token"
        connections[idx]["updatedAt"] = now_iso()
        save_connections(connections)


# 设备代码内存存储 (重启丢失，但有效期只有15分钟)
_device_code_store: dict[str, dict[str, Any]] = {}


def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# --- 站点发现 ---

@app.get("/api/connections/{connection_id}/discover")
async def discover_sites(connection_id: str, search: str = "*"):
    conn = _get_connection(connection_id)
    graph = GraphClient()
    sites = await graph.discover_sites(conn, search)
    return {"sites": sites}


@app.get("/api/connections/{connection_id}/drives")
async def discover_drives(connection_id: str, site_id: str):
    conn = _get_connection(connection_id)
    graph = GraphClient()
    drives = await graph.discover_drives(conn, {"id": site_id})
    doc_drives = [d for d in drives if str(d.get("driveType", "")).lower() in ("", "documentlibrary", "business")]
    return {"drives": doc_drives}


# --- 挂载到 OpenList ---

@app.post("/api/mounts/batch")
async def batch_mount(body: dict[str, Any]):
    """选中文档库 → 调用 OpenList API 创建存储。"""
    connection_id = body.get("connectionId")
    items: list[dict[str, Any]] = body.get("items", [])
    if not connection_id or not items:
        raise AppError(400, "connectionId 和 items 必填")

    s = load_settings()
    if not s.get("openListUrl") or not s.get("openListApiKey"):
        raise AppError(400, "请先在「OpenList 设置」中配置地址和 API Key")

    conn = _get_connection(connection_id)
    ol = OpenListClient(s["openListUrl"], s["openListApiKey"])
    mounts = load_mounts()
    results = []

    for item in items:
        drive = item.get("drive", {})
        site = item.get("site", {})
        mount_path = build_mount_path(
            site.get("displayName") or site.get("name") or "Site",
            drive.get("name") or "Documents",
        )
        addition = build_onedrive_addition(conn, drive, site)

        # 调用 OpenList API 创建存储
        try:
            ol_result = await ol.create_storage(mount_path, "Onedrive", addition)
        except Exception as e:
            results.append({"mount_path": mount_path, "error": str(e), "site": site, "drive": drive})
            continue

        mount_id = "mount-" + hashlib.sha1(
            f"{connection_id}:{drive.get('id', '')}".encode()
        ).hexdigest()[:16]

        record = {
            "id": mount_id,
            "connectionId": connection_id,
            "mountPath": mount_path,
            "siteName": site.get("displayName") or site.get("name"),
            "driveName": drive.get("name"),
            "siteUrl": site.get("webUrl", ""),
            "openListResult": ol_result,
            "mountedAt": now_iso(),
        }
        existing = next((i for i, m in enumerate(mounts) if m.get("id") == mount_id), -1)
        if existing >= 0:
            mounts[existing] = record
        else:
            mounts.append(record)
        results.append(record)

    save_mounts(mounts)
    errors = [r for r in results if "error" in r]
    return {
        "ok": len(errors) == 0,
        "count": len(results),
        "errors": errors,
        "mounts": [r for r in results if "error" not in r],
    }


@app.post("/api/mounts/auto-mount-all")
async def auto_mount_all(body: dict[str, Any]):
    """一键全量挂载：发现所有站点 → 全部挂载到 OpenList。"""
    connection_id = body.get("connectionId")
    if not connection_id:
        raise AppError(400, "connectionId 必填")

    s = load_settings()
    if not s.get("openListUrl") or not s.get("openListApiKey"):
        raise AppError(400, "请先在「OpenList 设置」中配置地址和 API Key")

    conn = _get_connection(connection_id)
    ol = OpenListClient(s["openListUrl"], s["openListApiKey"])
    graph = GraphClient()

    sites = await graph.discover_sites(conn, body.get("search", "*"))
    if not sites:
        return {"count": 0, "sites": 0, "mounts": []}

    mounts = load_mounts()
    results = []
    errors = []

    for site in sites:
        try:
            drives = await graph.discover_drives(conn, site)
        except Exception:
            continue
        doc_drives = [d for d in drives if str(d.get("driveType", "")).lower() in ("", "documentlibrary", "business")]
        for drive in doc_drives:
            mount_path = build_mount_path(
                site.get("displayName") or site.get("name") or "Site",
                drive.get("name") or "Documents",
            )
            addition = build_onedrive_addition(conn, drive, site)
            try:
                ol_result = await ol.create_storage(mount_path, "Onedrive", addition)
            except Exception as e:
                errors.append({"mount_path": mount_path, "error": str(e)})
                continue

            mount_id = "mount-" + hashlib.sha1(
                f"{connection_id}:{drive.get('id', '')}".encode()
            ).hexdigest()[:16]
            record = {
                "id": mount_id,
                "connectionId": connection_id,
                "mountPath": mount_path,
                "siteName": site.get("displayName") or site.get("name"),
                "driveName": drive.get("name"),
                "siteUrl": site.get("webUrl", ""),
                "openListResult": ol_result,
                "mountedAt": now_iso(),
            }
            existing = next((i for i, m in enumerate(mounts) if m.get("id") == mount_id), -1)
            if existing >= 0:
                mounts[existing] = record
            else:
                mounts.append(record)
            results.append(record)

    save_mounts(mounts)
    return {"count": len(results), "sites": len(sites), "errors": errors, "mounts": results}


@app.post("/api/connections/{connection_id}/mount-by-url")
async def mount_by_url(connection_id: str, body: dict[str, Any]):
    """通过站点 URL 挂载。"""
    conn = _get_connection(connection_id)
    site_url = str(body.get("siteUrl", "")).strip()
    if not site_url:
        raise AppError(400, "必须填写 SharePoint 站点 URL")

    s = load_settings()
    if not s.get("openListUrl") or not s.get("openListApiKey"):
        raise AppError(400, "请先在「OpenList 设置」中配置地址和 API Key")

    ol = OpenListClient(s["openListUrl"], s["openListApiKey"])
    graph = GraphClient()
    site = await graph.resolve_site_by_url(conn, site_url)
    drives = await graph.discover_drives(conn, site)
    doc_drives = [d for d in drives if str(d.get("driveType", "")).lower() in ("", "documentlibrary", "business")]

    mounts = load_mounts()
    results = []
    for drive in doc_drives:
        mount_path = build_mount_path(
            site.get("displayName") or site.get("name") or "Site",
            drive.get("name") or "Documents",
        )
        addition = build_onedrive_addition(conn, drive, site)
        try:
            ol_result = await ol.create_storage(mount_path, "Onedrive", addition)
        except Exception as e:
            results.append({"mount_path": mount_path, "error": str(e)})
            continue
        mount_id = "mount-" + hashlib.sha1(f"{connection_id}:{drive.get('id','')}".encode()).hexdigest()[:16]
        record = {
            "id": mount_id,
            "connectionId": connection_id,
            "mountPath": mount_path,
            "siteName": site.get("displayName") or site.get("name"),
            "driveName": drive.get("name"),
            "siteUrl": site.get("webUrl", ""),
            "openListResult": ol_result,
            "mountedAt": now_iso(),
        }
        existing = next((i for i, m in enumerate(mounts) if m.get("id") == mount_id), -1)
        if existing >= 0:
            mounts[existing] = record
        else:
            mounts.append(record)
        results.append(record)
    save_mounts(mounts)
    return {"site": {"id": site.get("id"), "displayName": site.get("displayName"), "webUrl": site.get("webUrl")}, "mounts": results}


# --- 挂载记录管理 ---

@app.get("/api/mounts")
def list_mounts():
    return load_mounts()


@app.delete("/api/mounts/{mount_id}")
def delete_mount(mount_id: str):
    mounts = load_mounts()
    mounts = [m for m in mounts if m.get("id") != mount_id]
    save_mounts(mounts)
    return {"ok": True}


@app.delete("/api/mounts")
def clear_mounts():
    save_mounts([])
    return {"ok": True}


@app.get("/api/openlist/storage")
async def list_openlist_storage():
    """从 OpenList 查询当前已挂载的存储列表。"""
    s = load_settings()
    if not s.get("openListUrl") or not s.get("openListApiKey"):
        raise AppError(400, "请先配置 OpenList 设置")
    ol = OpenListClient(s["openListUrl"], s["openListApiKey"])
    items = await ol.list_storage()
    return {"storage": items}


# --- 工具函数 ---

def mask_connection(c: dict[str, Any]) -> dict[str, Any]:
    return {
        **c,
        "clientSecret": mask_secret(c.get("clientSecret", "")),
        "refreshToken": mask_secret(c.get("refreshToken", "")),
        "hasClientSecret": bool(c.get("clientSecret")),
        "hasRefreshToken": bool(c.get("refreshToken")),
    }


# --- 静态文件 ---

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"   SP → OpenList 自动挂载管理器 v2")
    print(f"   地址: http://{HOST}:{PORT}")
    print(f"   数据: {DATA_DIR}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
