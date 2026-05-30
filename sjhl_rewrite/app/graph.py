from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx

from .config import AUTH_BASE_URL, GRAPH_BASE_URL, auto_chunk_size, normalize_chunk_size
from .utils import encode_graph_drive_path, join_remote_path

ProgressCallback = Callable[[int, int, float, str], None]


class GraphClient:
    def __init__(self):
        self._token_cache: dict[str, dict[str, Any]] = {}

    def graph_base_url(self, profile: dict[str, Any]) -> str:
        return (profile.get("graph_base_url") or profile.get("graphBaseUrl") or GRAPH_BASE_URL).rstrip("/")

    def auth_base_url(self, profile: dict[str, Any]) -> str:
        return (profile.get("auth_base_url") or profile.get("authBaseUrl") or AUTH_BASE_URL).rstrip("/")

    def upload_chunk_size(self, total_size: int) -> int:
        return normalize_chunk_size(auto_chunk_size(total_size))

    async def token(self, profile: dict[str, Any]) -> str:
        tenant_id = profile.get("tenant_id") or profile.get("tenantId")
        client_id = profile.get("client_id") or profile.get("clientId")
        client_secret = profile.get("client_secret") or profile.get("clientSecret")
        if not tenant_id or not client_id or not client_secret:
            raise ValueError("SP 配置缺少 tenant_id/client_id/client_secret")

        graph_origin = self.graph_base_url(profile).split("/v1.0")[0]
        cache_key = f"{tenant_id}:{client_id}:{graph_origin}"
        cached = self._token_cache.get(cache_key)
        if cached and cached["expires_at"] > time.time() + 90:
            return cached["access_token"]

        url = f"{self.auth_base_url(profile)}/{tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": f"{graph_origin}/.default",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=20)) as client:
            response = await client.post(url, data=data)
        payload = response.json() if response.text else {}
        if response.status_code >= 400:
            raise ValueError(f"SP 认证失败 HTTP {response.status_code}: {payload}")
        access_token = payload.get("access_token")
        if not access_token:
            raise ValueError(f"SP 认证返回缺少 access_token: {payload}")
        self._token_cache[cache_key] = {
            "access_token": access_token,
            "expires_at": time.time() + int(payload.get("expires_in") or 3600),
        }
        return access_token

    async def request(self, profile: dict[str, Any], method: str, api_path: str, body: dict[str, Any] | None = None):
        token = await self.token(profile)
        url = api_path if api_path.startswith("http") else f"{self.graph_base_url(profile)}{api_path}"
        headers = {"authorization": f"Bearer {token}"}
        if body is not None:
            headers["content-type"] = "application/json"
        async with httpx.AsyncClient(timeout=None) as client:
            last_response: httpx.Response | None = None
            for attempt in range(5):
                response = await client.request(method, url, headers=headers, json=body)
                last_response = response
                if response.status_code not in (408, 409, 423, 429, 500, 502, 503, 504):
                    break
                retry_after = int(response.headers.get("retry-after") or 0)
                await asyncio.sleep(retry_after or min(20, 1.5 * (attempt + 1)))
            response = last_response
        if response is None:
            raise ValueError("Graph 请求未返回响应")
        try:
            payload = response.json() if response.text else None
        except ValueError:
            payload = response.text
        if response.status_code >= 400:
            raise ValueError(f"Graph 请求失败 HTTP {response.status_code}: {payload}")
        return payload

    async def create_upload_session(self, profile: dict[str, Any], drive_id: str, remote_path: str, conflict: str = "replace"):
        encoded = encode_graph_drive_path(remote_path)
        body = {"item": {"@microsoft.graph.conflictBehavior": conflict, "name": remote_path.split("/")[-1]}}
        return await self.request(
            profile,
            "POST",
            f"/drives/{quote(drive_id, safe='')}/root:/{encoded}:/createUploadSession",
            body,
        )

    async def put_chunk(self, client: httpx.AsyncClient, upload_url: str, chunk: bytes, start: int, total: int) -> dict[str, Any] | None:
        end = start + len(chunk) - 1
        headers = {"content-length": str(len(chunk)), "content-range": f"bytes {start}-{end}/{total}"}
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                response = await client.put(upload_url, headers=headers, content=chunk)
                if response.status_code in (200, 201, 202):
                    return response.json() if response.text else None
                if response.status_code not in (408, 409, 423, 429, 500, 502, 503, 504):
                    raise ValueError(f"Graph 分片上传失败 HTTP {response.status_code}: {response.text[:500]}")
                retry_after = int(response.headers.get("retry-after") or 0)
                await asyncio.sleep(retry_after or min(20, 1.5 * (attempt + 1)))
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as exc:
                last_error = exc
                await asyncio.sleep(min(20, 1.5 * (attempt + 1)))
        if last_error:
            raise ValueError(f"Graph 分片上传连接失败: {last_error}") from last_error
        raise ValueError("Graph 分片上传重试耗尽")

    async def upload_local_file(
        self,
        profile: dict[str, Any],
        file_path: str | Path,
        remote_dir: str,
        file_name: str,
        size: int,
        on_progress: ProgressCallback | None = None,
        conflict: str = "replace",
    ) -> dict[str, Any]:
        drive_id = profile.get("drive_id") or profile.get("driveId")
        if not drive_id:
            raise ValueError("SP 配置缺少 drive_id")
        root_path = profile.get("root_path") or profile.get("rootPath") or ""
        remote_path = join_remote_path(root_path, remote_dir, file_name)
        total = int(size or Path(file_path).stat().st_size)
        if total <= 0:
            return await self._upload_empty_file(profile, drive_id, remote_path, on_progress)

        session = await self.create_upload_session(profile, drive_id, remote_path, conflict)
        upload_url = session.get("uploadUrl")
        if not upload_url:
            raise ValueError(f"Graph 未返回 uploadUrl: {session}")

        chunk_size = self.upload_chunk_size(total)
        sha256 = hashlib.sha256()
        uploaded = 0
        started = time.monotonic()
        last_result: dict[str, Any] | None = None

        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
            with Path(file_path).open("rb") as stream:
                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    start = uploaded
                    sha256.update(chunk)
                    last_result = await self.put_chunk(client, upload_url, chunk, start, total)
                    uploaded += len(chunk)
                    elapsed = max(time.monotonic() - started, 0.001)
                    speed = uploaded / elapsed
                    if on_progress:
                        on_progress(uploaded, total, speed, "上传")

        item = last_result or {}
        return {
            "item": item,
            "remotePath": remote_path,
            "fileName": file_name,
            "size": total,
            "sha256": sha256.hexdigest(),
            "webUrl": item.get("webUrl") if isinstance(item, dict) else "",
        }

    async def _upload_empty_file(
        self,
        profile: dict[str, Any],
        drive_id: str,
        remote_path: str,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        token = await self.token(profile)
        encoded = encode_graph_drive_path(remote_path)
        url = f"{self.graph_base_url(profile)}/drives/{quote(drive_id, safe='')}/root:/{encoded}:/content"
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=20)) as client:
            response = await client.put(
                url,
                headers={
                    "authorization": f"Bearer {token}",
                    "content-type": "application/octet-stream",
                    "content-length": "0",
                },
                content=b"",
            )
        payload = response.json() if response.text else {}
        if response.status_code >= 400:
            raise ValueError(f"空文件上传失败 HTTP {response.status_code}: {payload}")
        if on_progress:
            on_progress(0, 0, 0.0, "上传")
        return {"item": payload, "remotePath": remote_path, "fileName": remote_path.split("/")[-1], "size": 0, "sha256": hashlib.sha256(b"").hexdigest()}

