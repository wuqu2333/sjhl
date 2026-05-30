from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

from .config import CLOUDDRIVE_AUTHORIZE_URL, CLOUDDRIVE_CLIENT_ID, CLOUDDRIVE_REDIRECT_URI, DEFAULT_USER_AGENT

try:
    from p115client import P115Client
except Exception:  # pragma: no cover
    P115Client = None


def response_json_or_error(response: httpx.Response, context: str) -> dict[str, Any]:
    if not response.text.strip():
        raise ValueError(f"{context} 返回空响应，HTTP {response.status_code}")
    try:
        payload = response.json()
    except Exception as exc:
        snippet = " ".join(response.text.split())[:300]
        raise ValueError(f"{context} 返回非 JSON，HTTP {response.status_code}: {snippet}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{context} 返回格式无效")
    return payload


class Pan115Client:
    def __init__(self):
        self._refresh_cache: dict[str, dict[str, Any]] = {}
        self._refresh_block_until: dict[str, float] = {}
        self._refresh_lock = asyncio.Lock()
        self.open_delay_seconds = 0.5
        self.cookie_delay_seconds = 0.5

    def clouddrive_authorize_url(self, state: str) -> str:
        return CLOUDDRIVE_AUTHORIZE_URL + "?" + urlencode(
            {
                "client_id": CLOUDDRIVE_CLIENT_ID,
                "redirect_uri": CLOUDDRIVE_REDIRECT_URI,
                "response_type": "code",
                "state": state or CLOUDDRIVE_REDIRECT_URI,
            }
        )

    async def clouddrive_get_tokens_by_cookie(self, cookie: str) -> dict[str, str]:
        if P115Client is None:
            raise ValueError("当前环境未安装 p115client，无法使用 Cookie 自动授权 CloudDrive")
        if not cookie:
            raise ValueError("115 Cookie 不能为空")

        def work() -> dict[str, str]:
            client = P115Client(cookie, check_for_relogin=True, ensure_cookies=True, app="chrome")
            resp = client.login_authorize_open(
                {
                    "client_id": CLOUDDRIVE_CLIENT_ID,
                    "redirect_uri": CLOUDDRIVE_REDIRECT_URI,
                    "state": CLOUDDRIVE_REDIRECT_URI,
                }
            )
            final = client.request(resp["url"], follow_redirects=False, parse=lambda r, c: r)
            location = final.headers.get("location", "")
            query = dict(parse_qsl(urlsplit(location).query))
            if not query.get("access_token"):
                raise ValueError(f"CloudDrive 授权失败: {query or location}")
            return {"accessToken": query["access_token"], "refreshToken": query.get("refresh_token", "")}

        return await asyncio.to_thread(work)

    async def refresh_open_token(self, refresh_token: str) -> dict[str, str]:
        if not refresh_token:
            raise ValueError("115 refresh_token 不能为空")
        now = time.monotonic()
        cached = self._refresh_cache.get(refresh_token)
        if cached and now - float(cached.get("at") or 0) < 600:
            return {"accessToken": cached["accessToken"], "refreshToken": cached["refreshToken"]}
        blocked_until = self._refresh_block_until.get(refresh_token, 0)
        if blocked_until > now:
            raise ValueError("115 Token 刷新过于频繁，已临时暂停刷新")
        async with self._refresh_lock:
            cached = self._refresh_cache.get(refresh_token)
            now = time.monotonic()
            if cached and now - float(cached.get("at") or 0) < 600:
                return {"accessToken": cached["accessToken"], "refreshToken": cached["refreshToken"]}
            blocked_until = self._refresh_block_until.get(refresh_token, 0)
            if blocked_until > now:
                raise ValueError("115 Token 刷新过于频繁，已临时暂停刷新")
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=20)) as client:
                response = await client.post(
                    "https://passportapi.115.com/open/refreshToken",
                    data={"refresh_token": refresh_token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            payload = response_json_or_error(response, "115 Token 刷新")
            if payload.get("code") != 0:
                message = payload.get("message") or payload.get("error") or "未知错误"
                if "frequent" in str(message).lower() or "频繁" in str(message):
                    self._refresh_block_until[refresh_token] = time.monotonic() + 300
                raise ValueError(f"Token 刷新失败: {message}")
            data = payload.get("data") or {}
            result = {"accessToken": data.get("access_token", ""), "refreshToken": data.get("refresh_token", "")}
            if not result["accessToken"]:
                raise ValueError(f"115 Token 刷新返回缺少 access_token: {payload}")
            self._refresh_cache[refresh_token] = {**result, "at": time.monotonic()}
            return result

    async def down_url_auto(self, account: dict[str, Any], pick_code: str, user_agent: str | None = None) -> dict[str, Any]:
        user_agent = user_agent or account.get("user_agent") or DEFAULT_USER_AGENT
        last_error = ""
        if account.get("access_token") or account.get("refresh_token"):
            try:
                result = await self.down_url_open(
                    account.get("access_token") or "",
                    account.get("refresh_token") or "",
                    pick_code,
                    user_agent,
                )
                return {**result, "mode": "open"}
            except Exception as exc:
                last_error = f"Open: {exc}"
        if account.get("cookie"):
            try:
                result = await self.down_url_cookie(account["cookie"], pick_code, user_agent)
                return {**result, "mode": "cookie"}
            except Exception as exc:
                last_error = f"{last_error}; Cookie: {exc}" if last_error else f"Cookie: {exc}"
        raise ValueError(last_error or "115 账号没有可用认证信息")

    async def down_url_open(self, access_token: str, refresh_token: str, pick_code: str, user_agent: str) -> dict[str, Any]:
        token = access_token
        rt = refresh_token
        if not token:
            tokens = await self.refresh_open_token(rt)
            token = tokens["accessToken"]
            rt = tokens["refreshToken"]
        else:
            tokens = {"accessToken": token, "refreshToken": rt}
        try:
            return {**(await self._down_url_open_once(token, pick_code, user_agent)), **tokens}
        except Exception as first_error:
            if not rt:
                raise
            tokens = await self.refresh_open_token(rt)
            try:
                return {**(await self._down_url_open_once(tokens["accessToken"], pick_code, user_agent)), **tokens}
            except Exception as retry_error:
                raise ValueError(f"115 Open 下载链接获取失败: {first_error}; 刷新后仍失败: {retry_error}") from retry_error

    async def _down_url_open_once(self, access_token: str, pick_code: str, user_agent: str) -> dict[str, Any]:
        await asyncio.sleep(self.open_delay_seconds)
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=20)) as client:
            response = await client.post(
                "https://proapi.115.com/open/ufile/downurl",
                data={"pick_code": pick_code},
                headers={"Authorization": f"Bearer {access_token}", "User-Agent": user_agent},
            )
        payload = response_json_or_error(response, "115 Open 下载链接")
        if payload.get("state") is not True:
            raise ValueError(payload.get("message") or payload.get("error") or "下载链接获取失败")
        item = next(iter((payload.get("data") or {}).values()), None)
        if not isinstance(item, dict):
            raise ValueError("115 Open 未返回文件信息")
        url_data = item.get("url", {})
        url = url_data.get("url", "") if isinstance(url_data, dict) else str(url_data or "")
        headers = dict(url_data.get("headers") or {}) if isinstance(url_data, dict) else {}
        headers.setdefault("User-Agent", user_agent)
        headers.setdefault("Referer", "https://115.com/")
        return {
            "url": url,
            "headers": headers,
            "fileName": item.get("file_name") or "",
            "size": int(item.get("file_size") or 0),
            "sha1": item.get("sha1") or "",
            "pickCode": item.get("pick_code") or pick_code,
        }

    async def down_url_cookie(self, cookie: str, pick_code: str, user_agent: str) -> dict[str, Any]:
        if P115Client is None:
            raise ValueError("当前环境未安装 p115client，无法使用 Cookie 下载链接")
        if not cookie:
            raise ValueError("115 Cookie 不能为空")
        await asyncio.sleep(self.cookie_delay_seconds)

        def work() -> dict[str, Any]:
            client = P115Client(cookie, check_for_relogin=True, ensure_cookies=True, app="chrome")
            info = client.download_url(pick_code, strict=True, user_agent=user_agent, app="chrome", async_=False)
            url = str(info.geturl() if hasattr(info, "geturl") else info or "")
            if not url:
                raise ValueError("115 Cookie 未返回下载地址")
            headers = dict(info.get("headers") or {}) if hasattr(info, "get") else {}
            headers.setdefault("User-Agent", user_agent)
            headers.setdefault("Referer", "https://115.com/")
            return {
                "url": url,
                "headers": headers,
                "fileName": info.get("name") or "" if hasattr(info, "get") else "",
                "size": int(info.get("size") or 0) if hasattr(info, "get") else 0,
                "sha1": info.get("sha1") or "" if hasattr(info, "get") else "",
                "pickCode": info.get("pickcode") or pick_code if hasattr(info, "get") else pick_code,
            }

        return await asyncio.to_thread(work)

