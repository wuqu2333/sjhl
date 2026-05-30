from __future__ import annotations

import asyncio
import time
from urllib.parse import urlencode
from typing import Any

from p115client import P115Client, P115OpenClient
from utils.logging import logger


API_BASE_URL = "https://proapi.115.com"
CLOUDDRIVE_CLIENT_ID = 100195313
CLOUDDRIVE_REDIRECT_URI = "https://redirect115.zhenyunpan.com"
CLOUDDRIVE_AUTHORIZE_URL = "https://passportapi.115.com/open/authorize"
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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
API_DELAY_SETTING_KEYS = {
    "open": ("pan115OpenApiDelay", DEFAULT_OPEN_API_DELAY),
    "cookie": ("pan115CookieApiDelay", DEFAULT_COOKIE_API_DELAY),
}
API_DELAY_CATEGORY_KEYS = {
    "list": "listDelaySeconds",
    "rename": "renameDelaySeconds",
    "delete": "deleteDelaySeconds",
    "mutate": "mutateDelaySeconds",
    "down": "downDelaySeconds",
}


def response_json_or_error(response: Any, context: str) -> dict[str, Any]:
    status_code = getattr(response, "status_code", "?")
    content_type = getattr(response, "headers", {}).get("content-type", "")
    text = getattr(response, "text", "") or ""
    if not text.strip():
        raise ValueError(f"{context} 返回空响应，HTTP {status_code}，请检查 115 认证是否过期或网络是否被拦截")
    try:
        payload = response.json()
    except Exception as exc:
        snippet = " ".join(text.strip().split())[:200]
        raise ValueError(f"{context} 返回非 JSON 响应，HTTP {status_code}，Content-Type: {content_type}，内容: {snippet}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{context} 返回格式无效")
    return payload


def extract_115_down_url(payload: dict[str, Any], pick_code: str) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, dict):
        raise ValueError("115 downurl 返回格式无效")
    item = data.get(pick_code) or next(iter(data.values()), None)
    if not isinstance(item, dict):
        raise ValueError("115 downurl 未返回文件信息")
    url_value = item.get("url", {})
    if isinstance(url_value, dict):
        url_value = url_value.get("url")
    url_value = url_value or item.get("download_url") or item.get("file_url")
    if not url_value:
        raise ValueError("115 downurl 未返回下载地址")
    return {
        "url": url_value,
        "fileName": item.get("file_name") or item.get("name") or "",
        "size": int(item.get("file_size") or item.get("size") or 0),
        "sha1": item.get("sha1") or "",
        "pickCode": item.get("pick_code") or item.get("pickcode") or pick_code,
    }


def p115_cookie_client(cookie: str) -> P115Client:
    if not cookie:
        raise ValueError("115 Cookie 不能为空")
    return P115Client(cookie, check_for_relogin=True, ensure_cookies=True, app="chrome")


def p115_open_client(access_token: str, refresh_token: str | None = "") -> P115OpenClient:
    if not access_token:
        raise ValueError("115 access token 不能为空")
    return P115OpenClient.from_token(access_token, refresh_token or "")


def clouddrive_authorize_url(state: str) -> str:
    if not state:
        raise ValueError("CloudDrive 授权回跳地址不能为空")
    return CLOUDDRIVE_AUTHORIZE_URL + "?" + urlencode(
        {"client_id": CLOUDDRIVE_CLIENT_ID, "redirect_uri": CLOUDDRIVE_REDIRECT_URI, "response_type": "code", "state": state}
    )


def p115_url_to_file(url_info: Any, pick_code: str, user_agent: str) -> dict[str, Any]:
    download_url = str(url_info.geturl() if hasattr(url_info, "geturl") else url_info or "")
    if not download_url:
        raise ValueError("115 downurl 未返回下载地址")
    headers = dict(url_info.get("headers") or {}) if hasattr(url_info, "get") else {}
    headers.setdefault("user-agent", user_agent)
    return {
        "url": download_url,
        "fileName": url_info.get("name") or "" if hasattr(url_info, "get") else "",
        "size": int(url_info.get("size") or 0) if hasattr(url_info, "get") else 0,
        "sha1": url_info.get("sha1") or "" if hasattr(url_info, "get") else "",
        "pickCode": url_info.get("pickcode") or pick_code if hasattr(url_info, "get") else pick_code,
        "headers": headers,
    }


def p115_attr_to_source_file(attr: dict[str, Any]) -> dict[str, Any]:
    name = str(attr.get("name") or attr.get("file_name") or "")
    relpath = str(attr.get("relpath") or attr.get("path") or name).strip("/")
    if not relpath:
        relpath = name
    return {
        "name": name,
        "relativePath": relpath,
        "pickCode": attr.get("pickcode") or attr.get("pick_code") or "",
        "size": int(attr.get("size") or attr.get("file_size") or 0),
        "sha1": attr.get("sha1") or "",
    }


def attr_to_listing_item(attr: dict[str, Any]) -> dict[str, Any]:
    return {
        "fid": str(attr.get("id", "")),
        "cid": str(attr.get("parent_id", "")),
        "name": str(attr.get("name", "")),
        "size": int(attr.get("size") or 0),
        "isDir": bool(attr.get("is_dir", False)),
        "pickCode": str(attr.get("pickcode") or attr.get("pick_code") or ""),
        "sha1": str(attr.get("sha1") or ""),
        "mtime": str(attr.get("mtime") or attr.get("user_utime") or ""),
    }


class Pan115Client:
    def __init__(self, base_url: str = API_BASE_URL, settings_store=None):
        self.base_url = base_url.rstrip("/")
        self.settings_store = settings_store
        self._refresh_lock = asyncio.Lock()
        self._refresh_cache: dict[str, dict[str, Any]] = {}
        self._refresh_block_until: dict[str, float] = {}
        self._api_delay_lock = asyncio.Lock()
        self._api_delay_last_at: dict[str, float] = {}

    def clouddrive_authorize_url(self, state: str) -> str:
        return clouddrive_authorize_url(state)

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """获取115用户信息（Open API）"""
        import httpx
        await self._wait_api_delay("open", "list")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.get(
                "https://proapi.115.com/open/user/info",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        data = resp.json()
        if data.get("state") is not True:
            raise ValueError(f"获取用户信息失败: {data.get('message', '未知错误')}")
        info = data["data"]
        return {
            "userId": str(info.get("user_id", "")),
            "userName": str(info.get("user_name", "")),
            "avatar": str(info.get("user_face_m") or info.get("user_face_s", "")),
            "spaceTotal": int(info.get("rt_space_info", {}).get("all_total", {}).get("size", 0)),
            "spaceTotalFormat": str(info.get("rt_space_info", {}).get("all_total", {}).get("size_format", "")),
            "spaceUsed": int(info.get("rt_space_info", {}).get("all_use", {}).get("size", 0)),
            "spaceUsedFormat": str(info.get("rt_space_info", {}).get("all_use", {}).get("size_format", "")),
            "vipName": str(info.get("vip_info", {}).get("level_name", "")),
            "vipExpire": int(info.get("vip_info", {}).get("expire", 0)),
        }

    async def move_files(self, access_token: str, file_ids: list[str], to_cid: str) -> dict[str, Any]:
        """批量移动文件（Open API: /open/ufile/move）"""
        import httpx
        await self._wait_api_delay("open", "mutate")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.post(
                "https://proapi.115.com/open/ufile/move",
                data={"file_ids": ",".join(file_ids), "to_cid": to_cid},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        result = resp.json()
        if result.get("state") is not True:
            raise ValueError(f"移动文件失败: {result.get('message', '未知错误')}")
        return {"ok": True}

    async def copy_files(self, access_token: str, file_ids: list[str], target_pid: str, no_duplicate: bool = False) -> dict[str, Any]:
        """批量复制文件（Open API: /open/ufile/copy）"""
        import httpx
        data: dict[str, str] = {"pid": target_pid, "file_id": ",".join(file_ids)}
        if no_duplicate:
            data["nodupli"] = "1"
        await self._wait_api_delay("open", "mutate")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.post(
                "https://proapi.115.com/open/ufile/copy",
                data=data,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        result = resp.json()
        if result.get("state") is not True:
            raise ValueError(f"复制文件失败: {result.get('message', '未知错误')}")
        return {"ok": True}

    async def search_files(self, access_token: str, keyword: str, cid: str = "", limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """搜索文件（Open API: /open/ufile/search）"""
        import httpx
        params: dict[str, Any] = {"search_value": keyword, "limit": limit, "offset": offset}
        if cid:
            params["cid"] = int(cid)
        await self._wait_api_delay("open", "list")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.get(
                "https://proapi.115.com/open/ufile/search",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        data = resp.json()
        if data.get("state") is not True:
            raise ValueError(f"搜索文件失败: {data.get('message', '未知错误')}")
        items: list[dict[str, Any]] = []
        for f in data.get("data", []):
            items.append({
                "fileId": str(f.get("file_id", "")),
                "fileName": str(f.get("file_name", "")),
                "size": int(f.get("file_size") or 0),
                "sha1": str(f.get("sha1", "")),
                "pickCode": str(f.get("pick_code", "")),
                "parentId": str(f.get("parent_id", "")),
                "isDir": str(f.get("file_category", "1")) == "0",
                "updateTime": str(f.get("user_utime", "")),
            })
        return items

    async def update_file(self, access_token: str, file_id: str, name: str = "", star: str = "") -> dict[str, Any]:
        """更新文件名或星标（Open API: /open/ufile/update）"""
        import httpx
        data: dict[str, str] = {"file_id": file_id}
        if name:
            data["file_name"] = name
        if star in ("0", "1"):
            data["star"] = star
        await self._wait_api_delay("open", "rename")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.post(
                "https://proapi.115.com/open/ufile/update",
                data=data,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        result = resp.json()
        if result.get("state") is not True:
            raise ValueError(f"更新文件失败: {result.get('message', '未知错误')}")
        return {"fileName": str(result["data"].get("file_name", "")), "star": str(result["data"].get("star", ""))}

    async def recycle_bin_del(self, access_token: str, file_ids: list[str] | None = None) -> dict[str, Any]:
        """批量删除回收站文件/清空回收站（Open API: /open/rb/del）"""
        import httpx
        data: dict[str, str] = {}
        if file_ids:
            data["tid"] = ",".join(file_ids[:1150])
        await self._wait_api_delay("open", "delete")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.post(
                "https://proapi.115.com/open/rb/del",
                data=data,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        result = resp.json()
        if result.get("state") is not True:
            raise ValueError(f"回收站操作失败: {result.get('message', '未知错误')}")
        return {"ok": True, "deleted": len(result.get("data", [])) if file_ids else "all"}

    async def delete_files(self, access_token: str, file_ids: list[str], parent_id: str = "0") -> list[str]:
        """批量删除文件/文件夹（Open API: /open/ufile/delete）"""
        import httpx
        await self._wait_api_delay("open", "delete")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.post(
                "https://proapi.115.com/open/ufile/delete",
                data={"file_ids": ",".join(file_ids), "parent_id": parent_id},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        data = resp.json()
        if data.get("state") is not True:
            raise ValueError(f"删除文件失败: {data.get('message', '未知错误')}")
        return data.get("data", [])

    async def create_folder(self, access_token: str, pid: str, name: str) -> dict[str, Any]:
        """新建文件夹（Open API: /open/folder/add）"""
        import httpx
        await self._wait_api_delay("open", "mutate")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.post(
                "https://proapi.115.com/open/folder/add",
                data={"pid": pid, "file_name": name},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        data = resp.json()
        if data.get("state") is not True:
            raise ValueError(f"创建文件夹失败: {data.get('message', '未知错误')}")
        return {"fileId": str(data["data"]["file_id"]), "fileName": str(data["data"]["file_name"])}

    async def get_file_info(self, access_token: str, file_id: str) -> dict[str, Any]:
        """获取文件/文件夹详情（Open API: /open/folder/get_info）"""
        import httpx
        await self._wait_api_delay("open", "list")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.get(
                "https://proapi.115.com/open/folder/get_info",
                params={"file_id": file_id},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        data = resp.json()
        if data.get("state") is not True:
            raise ValueError(f"获取文件信息失败: {data.get('message', '未知错误')}")
        d = data["data"]
        return {
            "fileId": str(d.get("file_id", "")),
            "fileName": str(d.get("file_name", "")),
            "isDir": str(d.get("file_category", "1")) == "0",
            "size": int(d.get("size_byte") or 0),
            "sha1": str(d.get("sha1", "")),
            "pickCode": str(d.get("pick_code", "")),
            "updateTime": str(d.get("utime", "")),
        }

    async def clouddrive_get_tokens(self, cookie: str) -> dict[str, str]:
        """使用 Cookie 自动授权 CloudDrive，获取 access_token + refresh_token"""
        from urllib.parse import parse_qsl, urlsplit
        logger.info("115 CloudDrive: 开始自动授权")
        client = self._cookie_client(cookie)
        resp = client.login_authorize_open({
            "client_id": CLOUDDRIVE_CLIENT_ID,
            "redirect_uri": CLOUDDRIVE_REDIRECT_URI,
            "state": f"{CLOUDDRIVE_REDIRECT_URI}",
        })
        resp = client.request(resp["url"], follow_redirects=False, parse=lambda r, c: r)
        query = dict(parse_qsl(urlsplit(resp.headers["location"]).query))
        if not query.get("access_token"):
            raise ValueError(f"CloudDrive 授权失败，Cookie 可能已过期: {query}")
        logger.info("115 CloudDrive: 授权成功")
        return {"accessToken": query["access_token"], "refreshToken": query.get("refresh_token", "")}

    async def refresh_open_token(self, refresh_token: str) -> dict[str, str]:
        """刷新 Open API token（POST /open/refreshToken, code=0 表示成功）"""
        import httpx
        if not refresh_token:
            raise ValueError("115 refresh token 不能为空")
        now = time.monotonic()
        cached = self._refresh_cache.get(refresh_token)
        if cached and now - float(cached.get("at") or 0) < 600:
            return {"accessToken": cached["accessToken"], "refreshToken": cached["refreshToken"]}
        blocked_until = self._refresh_block_until.get(refresh_token, 0)
        if blocked_until > now:
            raise ValueError("115 Token 刷新过于频繁，已临时暂停刷新，请稍后重试")
        async with self._refresh_lock:
            now = time.monotonic()
            cached = self._refresh_cache.get(refresh_token)
            if cached and now - float(cached.get("at") or 0) < 600:
                return {"accessToken": cached["accessToken"], "refreshToken": cached["refreshToken"]}
            blocked_until = self._refresh_block_until.get(refresh_token, 0)
            if blocked_until > now:
                raise ValueError("115 Token 刷新过于频繁，已临时暂停刷新，请稍后重试")
            logger.info("115 Token 刷新: 开始")
            async with httpx.AsyncClient(timeout=None) as h:
                resp = await h.post(
                    "https://passportapi.115.com/open/refreshToken",
                    data={"refresh_token": refresh_token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            data = response_json_or_error(resp, "115 Token 刷新")
            if data.get("code") != 0:
                logger.error(f"115 Token 刷新失败: {data}")
                message = data.get("message") or data.get("error", "未知错误")
                if "frequent" in str(message).lower() or "频繁" in str(message):
                    self._refresh_block_until[refresh_token] = time.monotonic() + 300
                raise ValueError(f"Token 刷新失败: {message}")
            logger.info("115 Token 刷新成功")
            result = {"accessToken": data["data"]["access_token"], "refreshToken": data["data"]["refresh_token"]}
            self._refresh_cache[refresh_token] = {**result, "at": time.monotonic()}
            return result

    async def list_recycle_bin(self, access_token: str) -> list[dict[str, Any]]:
        """列出回收站文件（Go SDK: /open/rb/list）"""
        import httpx
        await self._wait_api_delay("open", "list")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.get(
                "https://proapi.115.com/open/rb/list",
                params={"limit": 10000},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        data = resp.json()
        if data.get("state") is not True:
            raise ValueError(f"回收站列表失败: {data.get('message', '未知错误')}")
        items: list[dict[str, Any]] = []
        for f in data.get("data", []):
            items.append({
                "id": str(f.get("id") or f.get("file_id", "")),
                "name": str(f.get("n") or f.get("file_name", "")),
                "size": int(f.get("s") or f.get("file_size") or 0),
                "isDir": f.get("fc") == "0",
                "deletedAt": str(f.get("d") or f.get("del_time", "")),
            })
        return items

    async def revert_recycle_bin(self, access_token: str, file_ids: list[str]) -> dict[str, Any]:
        """恢复回收站文件（Go SDK: /open/rb/revert）"""
        import httpx
        await self._wait_api_delay("open", "mutate")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.post(
                "https://proapi.115.com/open/rb/revert",
                data={"rid": ",".join(file_ids)},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        result = resp.json()
        if result.get("state") is not True:
            raise ValueError(f"恢复回收站文件失败: {result.get('message', '未知错误')}")
        return {"ok": True}

    def _cookie_client(self, cookie: str) -> P115Client:
        return p115_cookie_client(cookie)

    def _open_client(self, access_token: str, refresh_token: str = "") -> P115OpenClient:
        return p115_open_client(access_token, refresh_token)

    def _api_delay_config(self, mode: str) -> dict[str, float]:
        settings_key, defaults = API_DELAY_SETTING_KEYS[mode]
        raw = {}
        if self.settings_store:
            try:
                raw = self.settings_store.get().get(settings_key) or {}
            except Exception:
                raw = {}

        def number(key: str) -> float:
            try:
                return max(0.0, float(raw.get(key, defaults[key])))
            except (TypeError, ValueError):
                return float(defaults[key])

        return {key: number(key) for key in defaults}

    async def _wait_api_delay(self, mode: str, category: str) -> None:
        config = self._api_delay_config(mode)
        multiplier = config["globalMultiplier"]
        global_delay = config["globalDelaySeconds"] * multiplier
        category_delay = config[API_DELAY_CATEGORY_KEYS[category]] * multiplier
        if global_delay <= 0 and category_delay <= 0:
            return
        async with self._api_delay_lock:
            now = time.monotonic()
            global_key = f"{mode}:global"
            category_key = f"{mode}:{category}"
            target_at = max(
                self._api_delay_last_at.get(global_key, 0.0) + global_delay,
                self._api_delay_last_at.get(category_key, 0.0) + category_delay,
            )
            wait_seconds = target_at - now
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            stamped_at = time.monotonic()
            self._api_delay_last_at[global_key] = stamped_at
            self._api_delay_last_at[category_key] = stamped_at

    async def _refresh_open_if_needed(self, account: dict[str, Any]) -> dict[str, Any]:
        """尝试刷新 token，成功则更新账号存储并返回新 token"""
        rt = account.get("refreshToken") or ""
        if not rt:
            return account
        try:
            new_tokens = await self.refresh_open_token(rt)
            account["accessToken"] = new_tokens["accessToken"]
            account["refreshToken"] = new_tokens["refreshToken"]
            # 持久化新 token
            from app.stores import Pan115AccountStore
            from config.settings import DATA_DIR
            store = Pan115AccountStore(DATA_DIR)
            store.upsert({"id": account["id"], "accessToken": new_tokens["accessToken"], "refreshToken": new_tokens["refreshToken"]})
            logger.info(f"115 Token 自动刷新成功")
            return account
        except Exception as e:
            logger.warning(f"115 Token 刷新失败: {e}")
            return account

    # --- Download ---

    async def down_url(self, access_token: str | None, pick_code: str, user_agent: str = DEFAULT_UA, refresh_token: str | None = "") -> dict[str, Any]:
        if not pick_code:
            raise ValueError("115 pick_code 不能为空")
        token = access_token or ""
        rt = refresh_token or ""
        if not token and not rt:
            raise ValueError("115 access token 不能为空")
        if not token:
            tokens = await self.refresh_open_token(rt)
            token = tokens["accessToken"]
            rt = tokens["refreshToken"]
        else:
            tokens = {"accessToken": token, "refreshToken": rt}
        try:
            result = await self._down_url_open(token, pick_code, user_agent)
            return {**result, **tokens}
        except Exception as first_error:
            if not rt:
                raise
            tokens = await self.refresh_open_token(rt)
            try:
                result = await self._down_url_open(tokens["accessToken"], pick_code, user_agent)
            except Exception as retry_error:
                raise ValueError(f"115 Open 下载链接获取失败: {first_error}; 刷新后重试失败: {retry_error}") from retry_error
            return {**result, **tokens}

    async def down_url_by_cookie(self, cookie: str, pick_code: str, user_agent: str = DEFAULT_UA) -> dict[str, Any]:
        if not pick_code:
            raise ValueError("115 pick_code 不能为空")
        await self._wait_api_delay("cookie", "down")
        client = self._cookie_client(cookie)
        url_info = await client.download_url(pick_code, strict=True, user_agent=user_agent, app="chrome", async_=True)
        return p115_url_to_file(url_info, pick_code, user_agent)

    async def down_url_auto(self, account: dict[str, Any], pick_code: str, user_agent: str = DEFAULT_UA) -> dict[str, Any]:
        """优先 Open API 下载；access token 失败后才刷新，再失败才降级 Cookie。"""
        last_err = ""
        if account.get("accessToken") or account.get("refreshToken"):
            try:
                result = await self.down_url(
                    account.get("accessToken") or "",
                    pick_code,
                    user_agent,
                    account.get("refreshToken") or "",
                )
                if account.get("id") and (
                    result.get("accessToken") != account.get("accessToken")
                    or result.get("refreshToken") != account.get("refreshToken")
                ):
                    from app.stores import Pan115AccountStore
                    from config.settings import DATA_DIR

                    Pan115AccountStore(DATA_DIR).upsert(
                        {
                            "id": account["id"],
                            "accessToken": result.get("accessToken") or "",
                            "refreshToken": result.get("refreshToken") or "",
                        }
                    )
                return {**result, "mode": "open"}
            except Exception as e:
                last_err = f"Open API: {str(e)[:200]}"
        if account.get("cookie"):
            try:
                result = await self.down_url_by_cookie(account["cookie"], pick_code, user_agent)
                return {**result, "mode": "cookie"}
            except Exception as e:
                last_err = f"{last_err}; Cookie: {str(e)[:200]}" if last_err else f"Cookie: {str(e)[:200]}"
        raise ValueError(last_err or "115 账号未配置有效的认证方式")

    async def _down_url_open(self, token: str, pick_code: str, user_agent: str) -> dict[str, Any]:
        """Open API 下载链接"""
        import httpx
        await self._wait_api_delay("open", "down")
        async with httpx.AsyncClient(timeout=None) as h:
            resp = await h.post(
                "https://proapi.115.com/open/ufile/downurl",
                data={"pick_code": pick_code},
                headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent},
            )
        data = response_json_or_error(resp, "Open API 下载链接")
        if data.get("state") is not True:
            raise ValueError(data.get("message", "下载链接获取失败"))
        item = next(iter(data.get("data", {}).values()), None)
        if not item:
            raise ValueError("下载链接为空")
        url = item.get("url", {})
        url_str = url.get("url", "") if isinstance(url, dict) else str(url or "")
        cdn_headers = dict(url.get("headers") or {}) if isinstance(url, dict) else {}
        cdn_headers.setdefault("User-Agent", user_agent)
        cdn_headers.setdefault("Referer", "https://115.com/")
        logger.info(
            f"115 Open 下载链接获取成功：pick_code={pick_code}，"
            f"file={item.get('file_name','')}，size={item.get('file_size',0)}，"
            f"url_type={type(url).__name__}，url_keys={list(url.keys()) if isinstance(url, dict) else 'n/a'}，"
            f"item_keys={list(item.keys())}，cdn_headers={list(cdn_headers.keys())}"
        )
        return {
            "url": url_str,
            "fileName": item.get("file_name", ""),
            "size": int(item.get("file_size") or 0),
            "sha1": item.get("sha1", ""),
            "pickCode": item.get("pick_code", pick_code),
            "headers": cdn_headers,
        }

    # --- Directory Listing ---

    async def list_dir_open(self, access_token: str, cid: str = "0", refresh_token: str = "", user_agent: str = DEFAULT_UA) -> list[dict[str, Any]]:
        """Open API 列目录（直接 httpx，无 ECDH）"""
        import httpx
        items: list[dict[str, Any]] = []
        offset = 0
        limit = 1150
        while True:
            async with httpx.AsyncClient(timeout=None) as h:
                await self._wait_api_delay("open", "list")
                resp = await h.get(
                    "https://proapi.115.com/open/ufile/files",
                    params={"cid": int(cid or 0), "limit": limit, "offset": offset, "show_dir": 1, "cur": 1, "asc": 1, "o": "file_name"},
                    headers={"Authorization": f"Bearer {access_token}", "User-Agent": user_agent},
                )
            data = response_json_or_error(resp, "Open API 目录列表")
            if data.get("state") is not True:
                raise ValueError(f"Open API 目录列表失败: {data.get('message', '未知错误')}")
            for f in data.get("data", []):
                fn = f.get("fn", "")
                fid = str(f.get("fid", ""))
                is_dir = f.get("fc") == "0"
                items.append({
                    "fid": fid,
                    "cid": fid if is_dir else str(f.get("pid") or ""),
                    "name": str(fn),
                    "size": int(f.get("fs") or 0),
                    "isDir": is_dir,
                    "pickCode": str(f.get("pc") or f.get("pick_code") or ""),
                    "sha1": str(f.get("sha1") or f.get("sha") or ""),
                    "mtime": str(f.get("upt") or f.get("uet", "")),
                })
            count = int(data.get("count", 0))
            offset += len(data.get("data", []))
            if offset >= count or not data.get("data"):
                break
        return sorted(items, key=lambda x: (not x["isDir"], x["name"].lower()))

    async def list_dir_by_cookie(self, cookie: str, cid: str = "0", user_agent: str = DEFAULT_UA) -> list[dict[str, Any]]:
        """Cookie 方式列目录，使用 webapi.115.com 原生接口"""
        import httpx
        items: list[dict[str, Any]] = []
        next_url = "https://webapi.115.com/files"
        while next_url:
            async with httpx.AsyncClient(timeout=None) as h:
                await self._wait_api_delay("cookie", "list")
                if next_url.startswith("http"):
                    resp = await h.get(next_url, headers={"cookie": cookie, "user-agent": user_agent})
                else:
                    resp = await h.get(
                        "https://webapi.115.com/files",
                        params={"aid": "1", "cid": cid or "0", "limit": "10000", "show_dir": "1", "fc_mix": "1"},
                        headers={"cookie": cookie, "user-agent": user_agent},
                    )
            data = response_json_or_error(resp, "Cookie 目录列表")
            if data.get("state") is not True:
                raise ValueError(f"115 目录列表失败: {data.get('message', '未知错误')}")
            for f in data.get("data", []):
                is_dir = f.get("fid", 0) == 0
                item_id = str(f.get("fid") or f.get("id") or f.get("cid", ""))
                item_cid = str(f.get("cid") or "")
                if not f.get("n"):
                    continue
                items.append({
                    "fid": item_id,
                    "cid": item_cid,
                    "name": str(f.get("n") or f.get("name", "")),
                    "size": int(f.get("s") or f.get("size") or 0),
                    "isDir": is_dir,
                    "pickCode": str(f.get("pc") or f.get("pick_code") or ""),
                    "sha1": str(f.get("sha") or f.get("sha1") or ""),
                    "mtime": str(f.get("te") or f.get("user_utime") or ""),
                })
            next_url = data.get("next_page_url", "") or ""
        return sorted(items, key=lambda x: (not x["isDir"], x["name"].lower()))

    async def list_dir_auto(self, account: dict[str, Any], cid: str = "0", user_agent: str = DEFAULT_UA) -> list[dict[str, Any]]:
        """优先 Open API 列目录，失败则刷新 token 重试，再失败降级 Cookie"""
        if account.get("accessToken"):
            try:
                return await self.list_dir_open(account["accessToken"], cid, account.get("refreshToken", ""), user_agent)
            except Exception:
                # Token 过期，尝试刷新
                account = await self._refresh_open_if_needed(account)
                if account.get("accessToken"):
                    try:
                        return await self.list_dir_open(account["accessToken"], cid, account.get("refreshToken", ""), user_agent)
                    except Exception:
                        pass
        if account.get("cookie"):
            return await self.list_dir_by_cookie(account["cookie"], cid, user_agent)
        raise ValueError("115 账号未配置有效的认证方式")

    async def list_files_open(
        self,
        access_token: str,
        cid: str = "0",
        refresh_token: str = "",
        user_agent: str = DEFAULT_UA,
        recursive: bool = True,
    ) -> dict[str, Any]:
        """递归列出 Open API 目录文件，返回文件列表和可继续用于下载的 token。"""
        if not access_token:
            raise ValueError("115 access token 不能为空")

        async def collect(token: str) -> list[dict[str, Any]]:
            source_files: list[dict[str, Any]] = []

            async def walk(dir_cid: str, parent_path: str) -> None:
                children = await self.list_dir_open(token, dir_cid, "", user_agent)
                next_dirs: list[dict[str, str]] = []
                for item in children:
                    name = str(item.get("name") or "")
                    if not name:
                        continue
                    item_path = f"{parent_path}/{name}" if parent_path else name
                    if item.get("isDir"):
                        if recursive:
                            next_dirs.append({"cid": str(item.get("cid") or item.get("fid") or ""), "path": item_path})
                        continue
                    source_files.append(
                        {
                            "name": name,
                            "relativePath": item_path,
                            "pickCode": item.get("pickCode") or "",
                            "size": int(item.get("size") or 0),
                            "sha1": item.get("sha1") or "",
                        }
                    )
                for directory in next_dirs:
                    if directory["cid"]:
                        await walk(directory["cid"], directory["path"])

            await walk(cid or "0", "")
            return source_files

        try:
            return {
                "provider": "115-open",
                "files": await collect(access_token),
                "accessToken": access_token,
                "refreshToken": refresh_token,
            }
        except Exception:
            if not refresh_token:
                raise
            tokens = await self.refresh_open_token(refresh_token)
            return {
                "provider": "115-open",
                "files": await collect(tokens["accessToken"]),
                "accessToken": tokens["accessToken"],
                "refreshToken": tokens["refreshToken"],
            }

    async def list_files_auto(
        self,
        account: dict[str, Any],
        cid: str = "0",
        user_agent: str = DEFAULT_UA,
        recursive: bool = True,
    ) -> dict[str, Any]:
        """优先 Open API 递归扫描，失败后降级 Cookie，并返回使用的认证方式。"""
        last_error = ""
        if account.get("accessToken"):
            try:
                result = await self.list_files_open(
                    account["accessToken"],
                    cid,
                    account.get("refreshToken") or "",
                    user_agent,
                    recursive,
                )
                if account.get("id") and (
                    result.get("accessToken") != account.get("accessToken")
                    or result.get("refreshToken") != account.get("refreshToken")
                ):
                    from app.stores import Pan115AccountStore
                    from config.settings import DATA_DIR

                    Pan115AccountStore(DATA_DIR).upsert(
                        {
                            "id": account["id"],
                            "accessToken": result.get("accessToken") or "",
                            "refreshToken": result.get("refreshToken") or "",
                        }
                    )
                return result
            except Exception as error:
                last_error = f"Open API: {error}"
                logger.warning(f"115 Open API 递归扫描失败，尝试 Cookie 降级: {error}")
        if account.get("cookie"):
            try:
                return {
                    "provider": "115-cookie",
                    "files": await self.list_files_by_cookie(account["cookie"], cid, user_agent, recursive),
                    "cookie": account["cookie"],
                }
            except Exception as error:
                last_error = f"{last_error}; Cookie: {error}" if last_error else f"Cookie: {error}"
        raise ValueError(last_error or "115 账号未配置有效的认证方式")

    # --- Recursive File Listing ---

    async def list_files_by_cookie(self, cookie: str, cid: str = "0", user_agent: str = DEFAULT_UA, recursive: bool = True) -> list[dict[str, Any]]:
        """递归列出所有文件（使用 webapi，用于同步/搬运）"""
        import httpx
        source_files: list[dict[str, Any]] = []

        async def walk(dir_cid: str, parent_path: str):
            """递归遍历目录树"""
            dirs: list[dict[str, Any]] = []
            async with httpx.AsyncClient(timeout=None) as h:
                await self._wait_api_delay("cookie", "list")
                resp = await h.get(
                    "https://webapi.115.com/files",
                    params={"aid": "1", "cid": dir_cid, "limit": "10000", "show_dir": "1", "fc_mix": "1"},
                    headers={"cookie": cookie, "user-agent": user_agent},
                )
            data = response_json_or_error(resp, "Cookie 递归文件列表")
            if data.get("state") is not True:
                return
            for f in data.get("data", []):
                fn = f.get("n") or f.get("name", "")
                if not fn:
                    continue
                is_dir = f.get("fid", 0) == 0
                dir_cid_val = f.get("cid", "")
                file_path = f"{parent_path}/{fn}" if parent_path else fn
                if is_dir:
                    dirs.append({"cid": dir_cid_val, "path": file_path})
                else:
                    source_files.append({
                        "name": fn,
                        "relativePath": file_path,
                        "pickCode": f.get("pc", ""),
                        "size": int(f.get("s") or 0),
                        "sha1": f.get("sha", ""),
                    })
            if recursive:
                for d in dirs:
                    await walk(d["cid"], d["path"])

        await walk(cid or "0", "")
        return source_files
