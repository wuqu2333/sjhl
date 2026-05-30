from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote, urlparse

import httpx

from .config import AUTH_BASE_URL, GRAPH_BASE_URL, UPLOAD_CHUNK_SIZE
from .utils import clean, encode_graph_drive_path, join_remote_path
from utils.logging import logger


EXCLUDED_DISCOVERY_SITE_NAMES = {"team site", "communication site"}
EXCLUDED_DISCOVERY_SITE_PATHS = {"/", "/search", "/sites/contenttypehub"}
GRAPH_CHUNK_UNIT = 320 * 1024
GRAPH_MAX_CHUNK_SIZE = 191 * GRAPH_CHUNK_UNIT  # Graph 要求单个分片小于 60 MiB。
SMALL_UPLOAD_CHUNK_SIZE = 20 * 1024 * 1024
MID_UPLOAD_CHUNK_SIZE = 40 * 1024 * 1024
LARGE_UPLOAD_CHUNK_SIZE = 60 * 1024 * 1024
REMOTE_BUFFER_BYTES = 320 * 1024 * 1024
MAX_CONCURRENT_CHUNKS = 1  # 世纪互联 Graph API 不支持同一 session 并发分片，串行上传避免 416/409


def normalize_chunk_size(value: int) -> int:
    size = int(value or 0)
    if size <= 0:
        return 0
    size -= size % GRAPH_CHUNK_UNIT
    return min(GRAPH_MAX_CHUNK_SIZE, max(GRAPH_CHUNK_UNIT, size))


def auto_chunk_size(total_size: int) -> int:
    size = int(total_size or 0)
    if size and size <= 1024 * 1024 * 1024:
        return SMALL_UPLOAD_CHUNK_SIZE  # 20 MiB
    if size and size >= 20 * 1024 * 1024 * 1024:
        return LARGE_UPLOAD_CHUNK_SIZE  # 60 MiB
    return MID_UPLOAD_CHUNK_SIZE  # 40 MiB


def is_excluded_discovery_site(site: dict[str, Any]) -> bool:
    name = str(site.get("displayName") or site.get("name") or "").strip().lower()
    web_url = str(site.get("webUrl") or "").strip()
    parsed = urlparse(web_url)
    path = (parsed.path or "/").rstrip("/").lower() or "/"
    host = parsed.netloc.lower()
    return (
        name in EXCLUDED_DISCOVERY_SITE_NAMES
        or path in EXCLUDED_DISCOVERY_SITE_PATHS
        or "-my.sharepoint." in host
        or "/personal/" in path
    )


class GraphClient:
    def __init__(self, on_refresh_token=None, chunk_size: int = UPLOAD_CHUNK_SIZE):
        self.on_refresh_token = on_refresh_token
        self.configured_chunk_size = normalize_chunk_size(chunk_size)
        self.chunk_size = self.configured_chunk_size or MID_UPLOAD_CHUNK_SIZE
        self.token_cache: dict[str, dict[str, Any]] = {}

    def upload_chunk_size(self, total_size: int) -> int:
        return self.configured_chunk_size or normalize_chunk_size(auto_chunk_size(total_size))

    def queue_maxsize(self, chunk_size: int) -> int:
        if chunk_size <= 0:
            return 4
        return max(2, min(8, REMOTE_BUFFER_BYTES // chunk_size))

    def graph_base_url(self, profile: dict[str, Any]) -> str:
        return (profile.get("graphBaseUrl") or GRAPH_BASE_URL).rstrip("/")

    def auth_base_url(self, profile: dict[str, Any]) -> str:
        return (profile.get("authBaseUrl") or AUTH_BASE_URL).rstrip("/")

    async def token(self, profile: dict[str, Any]) -> str:
        graph_origin = self.graph_base_url(profile).split("/v1.0")[0]
        auth_mode = profile.get("authMode") or "client_credentials"
        cache_key = f"{auth_mode}:{profile.get('id') or profile.get('tenantId')}:{profile.get('clientId')}:{graph_origin}"
        cached = self.token_cache.get(cache_key)
        if cached and cached.get("expires_at", 0) > time.time() + 60:
            return cached["access_token"]
        params = {
            "client_id": profile.get("clientId"),
            "grant_type": "refresh_token" if auth_mode == "refresh_token" else "client_credentials",
            "scope": f"{graph_origin}/.default"
            if auth_mode == "client_credentials"
            else profile.get("scopes") or f"{graph_origin}/Files.ReadWrite.All {graph_origin}/Sites.ReadWrite.All offline_access",
        }
        if profile.get("clientSecret"):
            params["client_secret"] = profile["clientSecret"]
        if auth_mode == "refresh_token":
            params["refresh_token"] = profile.get("refreshToken")
            params["redirect_uri"] = profile.get("redirectUri") or "http://localhost"
        url = f"{self.auth_base_url(profile)}/{profile.get('tenantId')}/oauth2/v2.0/token"
        async with httpx.AsyncClient(timeout=None) as client:
            for attempt in range(4):
                response = await client.post(url, data=params)
                if response.status_code not in (409, 423, 429, 500, 502, 503, 504) or attempt == 3:
                    break
                retry_after = int(response.headers.get("retry-after") or 0)
                await asyncio.sleep(retry_after or (attempt + 1) * 1.2)
            payload = response.json()
        if response.status_code >= 400:
            raise ValueError(f"SP 认证失败: {payload}")
        if auth_mode == "client_credentials":
            claims = decode_jwt_payload(payload.get("access_token") or "")
            if not claims.get("roles"):
                raise ValueError(
                    "应用权限 token 没有 roles。请在世纪互联 Entra ID 应用注册中给 Microsoft Graph 添加"
                    "应用程序权限，例如 Sites.Read.All、Sites.ReadWrite.All、Files.ReadWrite.All，并点击管理员同意。"
                )
        if auth_mode == "refresh_token" and payload.get("refresh_token") and self.on_refresh_token:
            self.on_refresh_token(profile.get("id"), payload["refresh_token"])
        self.token_cache[cache_key] = {
            "access_token": payload["access_token"],
            "expires_at": time.time() + int(payload.get("expires_in") or 3600),
        }
        return payload["access_token"]

    async def request(self, profile: dict[str, Any], method: str, api_path: str, body: dict[str, Any] | None = None):
        token = await self.token(profile)
        url = api_path if api_path.startswith("http") else f"{self.graph_base_url(profile)}{api_path}"
        async with httpx.AsyncClient(timeout=None) as client:
            for attempt in range(4):
                response = await client.request(
                    method,
                    url,
                    headers={"authorization": f"Bearer {token}", **({"content-type": "application/json"} if body else {})},
                    json=body,
                )
                if response.status_code not in (429, 500, 502, 503, 504) or attempt == 3:
                    break
                retry_after = int(response.headers.get("retry-after") or 0)
                await asyncio.sleep(retry_after or (attempt + 1) * 1.2)
            text = response.text
        try:
            payload = response.json() if text else None
        except ValueError:
            payload = text
        if response.status_code >= 400:
            raise ValueError(f"Graph 请求失败 {response.status_code}: {payload}")
        return payload

    async def resolve_drive_id(self, profile: dict[str, Any]) -> str:
        if profile.get("driveId"):
            return profile["driveId"]
        if profile.get("siteId"):
            site_id = profile["siteId"]
        else:
            site_path = profile.get("sitePath") or ""
            if not site_path.startswith("/"):
                site_path = f"/{site_path}"
            site = await self.request(profile, "GET", f"/sites/{profile.get('siteHostname')}:{site_path}")
            site_id = site["id"]
        drives = await self.request(profile, "GET", f"/sites/{quote(site_id, safe='')}/drives")
        items = drives.get("value") or []
        wanted = (profile.get("libraryName") or "").lower()
        drive = (
            next((item for item in items if wanted and item.get("name", "").lower() == wanted), None)
            or next((item for item in items if item.get("name", "").lower() in ("documents", "shared documents", "文档")), None)
            or (items[0] if items else None)
        )
        if not drive:
            raise ValueError("未能找到文档库")
        return drive["id"]

    async def create_upload_session(self, profile: dict[str, Any], drive_id: str, remote_path: str, conflict: str = "fail"):
        encoded = encode_graph_drive_path(remote_path)
        try:
            return await self.request(
                profile,
                "POST",
                f"/drives/{quote(drive_id, safe='')}/root:/{encoded}:/createUploadSession",
                {"item": {"@microsoft.graph.conflictBehavior": conflict, "name": remote_path.split("/")[-1]}},
            )
        except ValueError as e:
            msg = str(e)
            if "nameAlreadyExists" in msg and conflict == "fail":
                logger.info(f"文件已存在，改用 replace 策略重试：{remote_path}")
                return await self.request(
                    profile,
                    "POST",
                    f"/drives/{quote(drive_id, safe='')}/root:/{encoded}:/createUploadSession",
                    {"item": {"@microsoft.graph.conflictBehavior": "replace", "name": remote_path.split("/")[-1]}},
                )
            raise

    async def upload_empty_file(self, profile: dict[str, Any], drive_id: str, remote_path: str, conflict: str = "fail"):
        token = await self.token(profile)
        encoded = encode_graph_drive_path(remote_path)
        url = (
            f"{self.graph_base_url(profile)}/drives/{quote(drive_id, safe='')}/root:/{encoded}:/content"
            f"?@microsoft.graph.conflictBehavior={quote(conflict, safe='')}"
        )
        async with httpx.AsyncClient(timeout=None) as client:
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
            raise ValueError(f"空文件上传失败 {response.status_code}: {payload}")
        return payload

    async def put_chunk(self, client: httpx.AsyncClient, upload_url: str, chunk: bytes, start: int, total: int):
        end = start + len(chunk) - 1
        for attempt in range(4):
            try:
                started = time.perf_counter()
                response = await client.put(
                    upload_url,
                    headers={"content-length": str(len(chunk)), "content-range": f"bytes {start}-{end}/{total}"},
                    content=chunk,
                )
                if response.status_code in (200, 201, 202):
                    elapsed = max(time.perf_counter() - started, 0.001)
                    speed = len(chunk) / elapsed / 1024 / 1024
                    logger.info(
                        f"Graph 分片上传完成：{start}-{end}/{total}，"
                        f"{len(chunk) / 1024 / 1024:.1f} MiB，耗时 {elapsed:.1f} 秒，速度 {speed:.1f} MiB/s"
                    )
                    return response.json() if response.text else None
                if response.status_code not in (423, 429, 500, 502, 503, 504) or attempt == 3:
                    raise ValueError(f"分片上传失败 {response.status_code}: {response.text}")
                await asyncio.sleep((attempt + 1) * 1.5)
            except (httpx.RemoteProtocolError, httpx.ConnectError) as e:
                if attempt == 3:
                    raise ValueError(f"分片上传连接失败: {e}")
                await asyncio.sleep((attempt + 1) * 0.5)

    async def upload_stream(
        self,
        profile: dict[str, Any],
        chunks: AsyncIterator[bytes],
        total_size: int,
        remote_dir: str,
        file_name: str,
        conflict: str = "fail",
        on_progress=None,
        chunk_size: int | None = None,
    ) -> dict[str, Any]:
        drive_id = await self.resolve_drive_id(profile)
        remote_path = join_remote_path(remote_dir, file_name)
        upload_chunk_size = normalize_chunk_size(chunk_size or 0) or self.upload_chunk_size(total_size)
        if total_size == 0:
            item = await self.upload_empty_file(profile, drive_id, remote_path, conflict)
            if on_progress:
                on_progress(0, 0)
            return {
                "item": item,
                "remotePath": remote_path,
                "size": 0,
                "sha256": hashlib.sha256(b"").hexdigest(),
            }
        session = await self.create_upload_session(profile, drive_id, remote_path, conflict)
        sha256 = hashlib.sha256()
        last_result = None
        uploaded = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as http:
            pending = b""
            batch: list[tuple[bytes, int]] = []
            offset = 0

            async for chunk in chunks:
                sha256.update(chunk)
                pending += chunk
                while len(pending) >= upload_chunk_size:
                    part = pending[:upload_chunk_size]
                    pending = pending[upload_chunk_size:]
                    batch.append((part, offset))
                    offset += len(part)
                    if len(batch) >= MAX_CONCURRENT_CHUNKS:
                        results = await asyncio.gather(*[
                            self.put_chunk(http, session["uploadUrl"], data, start, total_size)
                            for data, start in batch
                        ])
                        last_result = results[-1]
                        uploaded += sum(len(d) for d, _ in batch)
                        if on_progress:
                            on_progress(uploaded, total_size)
                        batch = []

            if pending:
                batch.append((pending, offset))

            if batch:
                results = await asyncio.gather(*[
                    self.put_chunk(http, session["uploadUrl"], data, start, total_size)
                    for data, start in batch
                ])
                last_result = results[-1]
                uploaded += sum(len(d) for d, _ in batch)
                if on_progress:
                    on_progress(uploaded, total_size)

        return {"item": last_result or {}, "remotePath": remote_path, "size": total_size, "sha256": sha256.hexdigest()}

    async def upload_local_file(
        self,
        profile: dict[str, Any],
        file_path: str,
        remote_dir: str,
        file_name: str,
        size: int,
        conflict: str = "fail",
        on_progress=None,
    ):
        chunk_size = self.upload_chunk_size(size)
        loop = asyncio.get_running_loop()

        async def chunks():
            fh = Path(file_path).open("rb")
            try:
                while True:
                    data = await loop.run_in_executor(None, fh.read, chunk_size)
                    if not data:
                        break
                    yield data
            finally:
                fh.close()

        return await self.upload_stream(profile, chunks(), size, remote_dir, file_name, conflict, on_progress, chunk_size)

    async def upload_remote_url(
        self,
        profile: dict[str, Any],
        source: dict[str, Any],
        remote_dir: str,
        file_name: str,
        conflict: str = "fail",
        on_progress=None,
        on_refresh_url=None,
    ):
        drive_id = await self.resolve_drive_id(profile)
        remote_path = join_remote_path(remote_dir, file_name)
        total_size = int(source.get("size") or 0)
        upload_chunk_size = self.upload_chunk_size(total_size)
        download_read_size = upload_chunk_size  # 与上传分片同大小，避免下载器被队列阻塞
        queue_maxsize = self.queue_maxsize(upload_chunk_size)
        logger.info(
            f"远程上传开始：文件={file_name}，目标={remote_path}，"
            f"分片大小={upload_chunk_size / 1024 / 1024:.1f} MiB，缓冲分片={queue_maxsize}"
        )
        if total_size < 0:
            raise ValueError("无法获取源文件大小，需在任务中填写 size")
        if total_size == 0:
            item = await self.upload_empty_file(profile, drive_id, remote_path, conflict)
            if on_progress:
                on_progress(0, 0)
            return {"item": item, "remotePath": remote_path, "size": 0, "sha256": hashlib.sha256(b"").hexdigest()}
        session = await self.create_upload_session(profile, drive_id, remote_path, conflict)
        logger.info(f"Graph 上传会话已创建：文件={file_name}，大小={total_size}")
        sha256 = hashlib.sha256()
        # 下载和上传通过队列并行执行，源站支持时用 HTTP Range 断点续读。
        queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        downloaded = [0]
        source_waiting = [0.0]

        async def downloader():
            nonlocal total_size
            started = time.perf_counter()
            retry_count = 0
            refresh_count = 0
            base_headers = dict(source.get("headers") or {})
            current_url = source["url"]
            async with httpx.AsyncClient(timeout=None) as client:
                while downloaded[0] < total_size:
                    headers = dict(base_headers)
                    if downloaded[0] > 0:
                        headers["Range"] = f"bytes={downloaded[0]}-"
                    logger.info(
                        f"下载请求：文件={file_name}，位置={downloaded[0]}/{total_size}，"
                        f"headers={[k for k in headers if k.lower() != 'authorization']}"
                    )
                    try:
                        async with client.stream("GET", current_url, headers=headers) as response:
                            if response.status_code in (401, 403):
                                if on_refresh_url and refresh_count < 3:
                                    refresh_count += 1
                                    logger.warning(
                                        f"下载链接已过期 {response.status_code}，尝试刷新：文件={file_name}，"
                                        f"位置={downloaded[0]}/{total_size}，刷新次数={refresh_count}"
                                    )
                                    new_source = await on_refresh_url()
                                    if new_source and new_source.get("url") and new_source["url"] != current_url:
                                        current_url = new_source["url"]
                                        base_headers = dict(new_source.get("headers") or {})
                                        retry_count = 0
                                        continue
                                raise ValueError(f"源文件读取失败 {response.status_code}，链接失效且无法刷新")
                            if response.status_code >= 400:
                                raise ValueError(f"源文件读取失败 {response.status_code}")
                            if downloaded[0] > 0 and response.status_code != 206:
                                raise ValueError(f"源文件不支持断点续读，HTTP {response.status_code}")
                            if not total_size and response.headers.get("content-length"):
                                total_size = int(response.headers["content-length"])
                            before = downloaded[0]
                            dl_buffer = b""
                            async for data in response.aiter_bytes(chunk_size=65536):
                                downloaded[0] += len(data)
                                dl_buffer += data
                                while len(dl_buffer) >= upload_chunk_size:
                                    part = dl_buffer[:upload_chunk_size]
                                    dl_buffer = dl_buffer[upload_chunk_size:]
                                    queued_at = time.perf_counter()
                                    await queue.put(part)
                                    source_waiting[0] += time.perf_counter() - queued_at
                            if dl_buffer:
                                queued_at = time.perf_counter()
                                await queue.put(dl_buffer)
                                source_waiting[0] += time.perf_counter() - queued_at
                            if downloaded[0] == before and downloaded[0] < total_size:
                                raise ValueError("源文件连接提前结束且没有读取到新数据")
                            retry_count = 0
                            refresh_count = 0
                    except (httpx.RemoteProtocolError, httpx.ReadError, httpx.TimeoutException, httpx.NetworkError, ValueError) as error:
                        if downloaded[0] >= total_size:
                            break
                        retry_count += 1
                        if retry_count > 6:
                            raise ValueError(
                                f"源文件读取中断，断点续读失败: 已读取 {downloaded[0]} / {total_size}, {error}"
                            ) from error
                        delay = min(30, retry_count * 3)
                        logger.warning(
                            f"源文件读取中断，准备断点续读：文件={file_name}，"
                            f"位置={downloaded[0]}/{total_size}，重试={retry_count}，错误={error}"
                        )
                        await asyncio.sleep(delay)
            elapsed = max(time.perf_counter() - started, 0.001)
            speed = downloaded[0] / elapsed / 1024 / 1024
            active_elapsed = max(elapsed - source_waiting[0], 0.001)
            source_speed = downloaded[0] / active_elapsed / 1024 / 1024
            logger.info(
                f"源文件读取完成：文件={file_name}，"
                f"{downloaded[0] / 1024 / 1024:.1f} MiB，耗时 {elapsed:.1f} 秒，平均 {speed:.1f} MiB/s，"
                f"源站有效读取 {active_elapsed:.1f} 秒，源站速度 {source_speed:.1f} MiB/s，"
                f"等待上传队列 {source_waiting[0]:.1f} 秒"
            )
            await queue.put(None)

        async def uploader(http_client: httpx.AsyncClient):
            pending = b""
            offset = 0
            batch: list[tuple[bytes, int]] = []
            last_result = None
            uploaded = 0
            while True:
                data = await queue.get()
                if data is None:
                    break
                sha256.update(data)
                pending += data
                while len(pending) >= upload_chunk_size:
                    part = pending[:upload_chunk_size]
                    pending = pending[upload_chunk_size:]
                    batch.append((part, offset))
                    offset += len(part)
                    if len(batch) >= MAX_CONCURRENT_CHUNKS:
                        results = await asyncio.gather(*[
                            self.put_chunk(http_client, session["uploadUrl"], data, start, total_size)
                            for data, start in batch
                        ])
                        last_result = results[-1]
                        uploaded += sum(len(d) for d, _ in batch)
                        if on_progress:
                            on_progress(uploaded, total_size)
                        batch = []
            if pending:
                batch.append((pending, offset))
            if batch:
                results = await asyncio.gather(*[
                    self.put_chunk(http_client, session["uploadUrl"], data, start, total_size)
                    for data, start in batch
                ])
                last_result = results[-1]
                uploaded += sum(len(d) for d, _ in batch)
                if on_progress:
                    on_progress(uploaded, total_size)
            return last_result

        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as upload_http:
            dl_task = asyncio.ensure_future(downloader())
            ul_task = asyncio.ensure_future(uploader(upload_http))
            try:
                await asyncio.gather(dl_task, ul_task)
            finally:
                for t in (dl_task, ul_task):
                    if not t.done():
                        t.cancel()
                await asyncio.gather(dl_task, ul_task, return_exceptions=True)
            result = ul_task.result()
        if downloaded[0] != total_size:
            raise ValueError(f"源文件大小不一致，已读取 {downloaded[0]}，预期 {total_size}")
        return {"item": result or {}, "remotePath": remote_path, "size": total_size, "sha256": sha256.hexdigest()}

    async def create_folder(self, profile: dict[str, Any], parent_dir: str, folder_name: str, conflict: str = "rename"):
        drive_id = await self.resolve_drive_id(profile)
        name = clean(folder_name).replace("\\", "/").split("/")[-1]
        if not name:
            raise ValueError("文件夹名称不能为空")
        parent = parent_dir.replace("\\", "/").strip("/")
        encoded = encode_graph_drive_path(parent)
        api_path = (
            f"/drives/{quote(drive_id, safe='')}/root:/{encoded}:/children"
            if encoded
            else f"/drives/{quote(drive_id, safe='')}/root/children"
        )
        return await self.request(
            profile,
            "POST",
            api_path,
            {
                "name": name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": conflict or "rename",
            },
        )

    async def list_remote_tree(self, profile: dict[str, Any], remote_dir: str = "") -> list[dict[str, Any]]:
        drive_id = await self.resolve_drive_id(profile)
        encoded = encode_graph_drive_path(remote_dir)
        first = f"/drives/{quote(drive_id, safe='')}/root:/{encoded}:/children" if encoded else f"/drives/{quote(drive_id, safe='')}/root/children"
        files: list[dict[str, Any]] = []

        async def walk(path_api: str, parent: str):
            next_path = path_api
            while next_path:
                try:
                    payload = await self.request(profile, "GET", next_path)
                except ValueError as error:
                    if "404" in str(error):
                        return
                    raise
                for item in payload.get("value") or []:
                    item_path = "/".join(part for part in [parent, item.get("name")] if part)
                    if item.get("folder"):
                        await walk(f"/drives/{quote(drive_id, safe='')}/items/{quote(item['id'], safe='')}/children", item_path)
                    elif item.get("file"):
                        hashes = item.get("file", {}).get("hashes", {})
                        files.append(
                            {
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "remotePath": item_path,
                                "size": int(item.get("size") or 0),
                                "sha1": hashes.get("sha1Hash") or "",
                                "sha256": hashes.get("sha256Hash") or "",
                                "quickXorHash": hashes.get("quickXorHash") or "",
                                "lastModifiedDateTime": item.get("lastModifiedDateTime") or "",
                                "webUrl": item.get("webUrl") or "",
                            }
                        )
                next_path = payload.get("@odata.nextLink") or ""

        await walk(first, remote_dir.strip("/"))
        return files

    async def list_remote_children(self, profile: dict[str, Any], remote_dir: str = "") -> list[dict[str, Any]]:
        drive_id = await self.resolve_drive_id(profile)
        clean_dir = remote_dir.replace("\\", "/").strip("/")
        encoded = encode_graph_drive_path(clean_dir)
        next_path = (
            f"/drives/{quote(drive_id, safe='')}/root:/{encoded}:/children"
            if encoded
            else f"/drives/{quote(drive_id, safe='')}/root/children"
        )
        items: list[dict[str, Any]] = []
        while next_path:
            try:
                payload = await self.request(profile, "GET", next_path)
            except ValueError as error:
                if "404" in str(error):
                    return []
                raise
            for item in payload.get("value") or []:
                is_folder = bool(item.get("folder"))
                item_path = "/".join(part for part in [clean_dir, item.get("name")] if part)
                parent_reference = item.get("parentReference") or {}
                file_info = item.get("file") or {}
                folder_info = item.get("folder") or {}
                hashes = file_info.get("hashes") or {}
                items.append(
                    {
                        "id": item.get("id"),
                        "driveId": parent_reference.get("driveId") or drive_id,
                        "name": item.get("name") or "",
                        "path": item_path,
                        "type": "folder" if is_folder else "file",
                        "size": int(item.get("size") or 0),
                        "childCount": int(folder_info.get("childCount") or 0),
                        "mimeType": file_info.get("mimeType") or "",
                        "sha1": hashes.get("sha1Hash") or "",
                        "sha256": hashes.get("sha256Hash") or "",
                        "quickXorHash": hashes.get("quickXorHash") or "",
                        "lastModifiedDateTime": item.get("lastModifiedDateTime") or "",
                        "webUrl": item.get("webUrl") or "",
                        "downloadUrl": item.get("@microsoft.graph.downloadUrl") or "",
                    }
                )
            next_path = payload.get("@odata.nextLink") or ""
        return sorted(items, key=lambda item: (item["type"] != "folder", item["name"].lower()))

    async def discover_sharepoint_sites(self, profile: dict[str, Any], search: str = "*") -> list[dict[str, Any]]:
        search_text = str(search or "*").strip()
        sites: list[dict[str, Any]] = []
        errors: list[str] = []
        sources = ["/sites/getAllSites", f"/sites?search={quote(search_text, safe='')}"]
        for source in sources:
            next_sites = source
            while next_sites:
                try:
                    sites_payload = await self.request(profile, "GET", next_sites)
                except ValueError as error:
                    if "403" in str(error) and profile.get("authMode") == "refresh_token":
                        raise ValueError(
                            "租户发现需要 Sites.Read.All 或 Sites.ReadWrite.All 权限。"
                            "委派 token 通常只有 Files.ReadWrite.All，只能用于已知 drive/文件操作，不能枚举整个租户的 SharePoint 站点。"
                        ) from error
                    errors.append(f"{source}: {error}")
                    logger.warning(f"SharePoint 站点发现来源失败：来源={source}，错误={error}")
                    break
                sites.extend(sites_payload.get("value") or [])
                next_sites = sites_payload.get("@odata.nextLink") or ""
        if not sites and errors:
            raise ValueError("租户发现失败: " + "; ".join(errors))
        deduped: dict[str, dict[str, Any]] = {}
        for site in sites:
            site_id = str(site.get("id") or site.get("webUrl") or "")
            if not site_id:
                continue
            if search_text and search_text != "*":
                haystack = " ".join(str(site.get(key) or "") for key in ("displayName", "name", "webUrl")).lower()
                if search_text.lower() not in haystack:
                    continue
            deduped[site_id] = site
        return list(deduped.values())

    async def discover_sharepoint_drives(self, profile: dict[str, Any], search: str = "*", documents_only: bool = True):
        sites = await self.discover_sharepoint_sites(profile, search)
        result: list[dict[str, Any]] = []
        for site in sites:
            if is_excluded_discovery_site(site):
                continue
            try:
                drive_items: list[dict[str, Any]] = []
                next_drives = f"/sites/{quote(site['id'], safe='')}/drives"
                while next_drives:
                    drives = await self.request(profile, "GET", next_drives)
                    drive_items.extend(drives.get("value") or [])
                    next_drives = drives.get("@odata.nextLink") or ""
            except Exception as error:
                logger.warning(f"跳过站点文档库发现：站点={site.get('webUrl') or site.get('id')}，错误={error}")
                continue
            for drive in drive_items:
                drive_type = str(drive.get("driveType") or "").lower()
                if documents_only and drive_type and drive_type not in ("documentlibrary", "business"):
                    continue
                quota = drive.get("quota") or {}
                result.append(
                    {
                        "siteId": site.get("id"),
                        "siteName": site.get("displayName") or site.get("name") or "",
                        "siteWebUrl": site.get("webUrl") or "",
                        "driveId": drive.get("id"),
                        "driveName": drive.get("name"),
                        "driveType": drive.get("driveType") or "",
                        "webUrl": drive.get("webUrl") or "",
                        "quotaTotal": int(quota.get("total") or 0),
                        "quotaUsed": int(quota.get("used") or 0),
                        "quotaRemaining": int(quota.get("remaining") or 0),
                        "quotaState": quota.get("state") or "",
                    }
                )
        logger.info(f"SharePoint 发现完成：站点数={len(sites)}，文档库数={len(result)}")
        return result


    async def delete_item(self, profile: dict[str, Any], item_id: str, drive_id: str = "") -> None:
        drive_id = drive_id or await self.resolve_drive_id(profile)
        await self.request(profile, "DELETE", f"/drives/{quote(drive_id, safe='')}/items/{quote(item_id, safe='')}")

    async def rename_item(self, profile: dict[str, Any], item_id: str, new_name: str, drive_id: str = "") -> dict[str, Any]:
        drive_id = drive_id or await self.resolve_drive_id(profile)
        return await self.request(
            profile, "PATCH",
            f"/drives/{quote(drive_id, safe='')}/items/{quote(item_id, safe='')}",
            {"name": new_name},
        )

    async def search_items(self, profile: dict[str, Any], query: str) -> list[dict[str, Any]]:
        drive_id = await self.resolve_drive_id(profile)
        items: list[dict[str, Any]] = []
        next_path = f"/drives/{quote(drive_id, safe='')}/root/search(q='{quote(query, safe='')}')"
        while next_path:
            payload = await self.request(profile, "GET", next_path)
            for item in payload.get("value") or []:
                parent_reference = item.get("parentReference") or {}
                parent_path = str(parent_reference.get("path") or "").strip()
                remote_parent = parent_path
                if "root:" in parent_path:
                    remote_parent = parent_path.split("root:", 1)[1].strip("/")
                remote_path = "/".join(part for part in [remote_parent, item.get("name", "")] if part)
                items.append({
                    "id": item.get("id", ""),
                    "driveId": parent_reference.get("driveId") or drive_id,
                    "name": item.get("name", ""),
                    "path": remote_path,
                    "size": int(item.get("size") or 0),
                    "isDir": bool(item.get("folder")),
                    "lastModifiedDateTime": item.get("lastModifiedDateTime", ""),
                    "webUrl": item.get("webUrl", ""),
                    "parentReference": remote_parent,
                })
            next_path = payload.get("@odata.nextLink") or ""
        return items


def decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return {}
