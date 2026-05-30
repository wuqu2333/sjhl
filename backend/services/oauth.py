from __future__ import annotations

import base64
import hashlib
import html
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from config.graph_regions import resolve_graph_region
from utils.paths import clean


def base64_urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def default_oauth_scopes(graph_base_url: str) -> str:
    graph_origin = graph_base_url.split("/v1.0")[0].rstrip("/")
    return " ".join(
        [
            "openid",
            "profile",
            "offline_access",
            f"{graph_origin}/Files.ReadWrite.All",
            f"{graph_origin}/Sites.ReadWrite.All",
        ]
    )


@dataclass
class OAuthFlow:
    state: str
    code_verifier: str
    created_at: float
    profile: dict[str, Any]
    auth_base_url: str
    graph_base_url: str
    scopes: str
    redirect_uri: str


class OAuthService:
    def __init__(self, profile_store, tenant_store):
        self.profile_store = profile_store
        self.tenant_store = tenant_store
        self.flows: dict[str, OAuthFlow] = {}
        self.completed: dict[str, dict[str, Any]] = {}

    def start(self, data: dict[str, Any]) -> dict[str, Any]:
        region = clean(data.get("region")) or "cn"
        defaults = resolve_graph_region(region)
        graph_base_url = clean(data.get("graphBaseUrl")) or defaults["graphBaseUrl"]
        auth_base_url = clean(data.get("authBaseUrl")) or defaults["authBaseUrl"]
        tenant_id = clean(data.get("tenantId")) or "common"
        client_id = clean(data.get("clientId"))
        if not client_id:
            raise ValueError("OAuth 登录必须填写 Client ID")
        redirect_uri = clean(data.get("redirectUri")) or "http://127.0.0.1:17651/api/oauth/callback"
        scopes = clean(data.get("scopes")) or default_oauth_scopes(graph_base_url)
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64_urlsafe(hashlib.sha256(code_verifier.encode("ascii")).digest())
        profile = {
            "name": clean(data.get("profileName")) or "OAuth SP",
            "authMode": "refresh_token",
            "region": region,
            "tenantId": tenant_id,
            "clientId": client_id,
            "clientSecret": clean(data.get("clientSecret")),
            "redirectUri": redirect_uri,
            "scopes": scopes,
            "graphBaseUrl": graph_base_url,
            "authBaseUrl": auth_base_url,
            "driveId": clean(data.get("driveId")),
            "siteId": clean(data.get("siteId")),
            "siteHostname": clean(data.get("siteHostname")),
            "sitePath": clean(data.get("sitePath")),
            "libraryName": clean(data.get("libraryName")),
            "rootPath": clean(data.get("rootPath")) or "/media",
        }
        self.flows[state] = OAuthFlow(
            state=state,
            code_verifier=code_verifier,
            created_at=time.time(),
            profile=profile,
            auth_base_url=auth_base_url,
            graph_base_url=graph_base_url,
            scopes=scopes,
            redirect_uri=redirect_uri,
        )
        self.cleanup()
        authorization_url = f"{auth_base_url.rstrip('/')}/{tenant_id}/oauth2/v2.0/authorize?{urlencode({
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'response_mode': 'query',
            'scope': scopes,
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        })}"
        return {
            "ok": True,
            "authorizationUrl": authorization_url,
            "state": state,
            "redirectUri": redirect_uri,
            "scopes": scopes,
        }

    async def callback(self, state: str, code: str) -> dict[str, Any]:
        flow = self.flows.pop(state, None)
        if not flow:
            raise ValueError("OAuth 登录状态已过期，请重新发起登录")
        token_url = f"{flow.auth_base_url.rstrip('/')}/{flow.profile['tenantId']}/oauth2/v2.0/token"
        token_data = {
            "client_id": flow.profile["clientId"],
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": flow.redirect_uri,
            "scope": flow.scopes,
            "code_verifier": flow.code_verifier,
        }
        if flow.profile.get("clientSecret"):
            token_data["client_secret"] = flow.profile["clientSecret"]
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(token_url, data=token_data)
            payload = response.json()
        if response.status_code >= 400:
            raise ValueError(f"OAuth token 交换失败: {payload}")
        if not payload.get("refresh_token"):
            raise ValueError("OAuth 登录未返回 refresh_token，请确认授权范围包含 offline_access")
        payload_data = {**flow.profile, "refreshToken": payload["refresh_token"]}
        result = self.save_token_payload(payload_data)
        self.completed[state] = result
        return result

    def save_token_payload(self, payload_data: dict[str, Any]) -> dict[str, Any]:
        if payload_data.get("driveId") or payload_data.get("siteId") or (
            payload_data.get("siteHostname") and payload_data.get("sitePath")
        ):
            saved = self.profile_store.upsert(payload_data)
            return {"ok": True, "type": "profile", "profile": saved}
        saved = self.tenant_store.upsert(
            {
                "name": payload_data["name"],
                "authMode": "refresh_token",
                "region": payload_data["region"],
                "tenantId": payload_data["tenantId"],
                "clientId": payload_data["clientId"],
                "clientSecret": payload_data.get("clientSecret") or "",
                "redirectUri": payload_data["redirectUri"],
                "refreshToken": payload_data["refreshToken"],
                "scopes": payload_data["scopes"],
                "graphBaseUrl": payload_data["graphBaseUrl"],
                "authBaseUrl": payload_data["authBaseUrl"],
                "defaultRootPath": payload_data.get("rootPath") or "/media",
                "importDocumentsOnly": True,
            }
        )
        return {"ok": True, "type": "tenantConnection", "connection": saved}

    def result(self, state: str) -> dict[str, Any] | None:
        return self.completed.get(state)

    def cleanup(self) -> None:
        now = time.time()
        self.flows = {key: value for key, value in self.flows.items() if now - value.created_at < 900}


def oauth_callback_html(result: dict[str, Any] | None = None, error: str = "") -> str:
    safe_error = html.escape(error)
    profile = (result or {}).get("profile") or {}
    connection = (result or {}).get("connection") or {}
    safe_profile_name = html.escape(str(profile.get("name") or ""))
    safe_connection_name = html.escape(str(connection.get("name") or ""))
    profile_id = html.escape(str(profile.get("id") or ""))
    connection_id = html.escape(str(connection.get("id") or ""))
    ok = "true" if result and result.get("ok") else "false"
    title = "OAuth 登录成功" if ok == "true" else "OAuth 登录失败"
    if ok == "true" and profile:
        message = f"已保存 SP 配置：{safe_profile_name}"
    elif ok == "true" and connection:
        message = f"已保存租户连接：{safe_connection_name}。请返回后台，在“租户连接”里点击“发现并导入”选择 SP。"
    else:
        message = safe_error
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 32px; }}
      .box {{ max-width: 560px; margin: 80px auto; border: 1px solid #d9d9d9; border-radius: 8px; padding: 24px; }}
      .ok {{ color: #1677ff; }}
      .err {{ color: #cf1322; }}
    </style>
  </head>
  <body>
    <div class="box">
      <h2 class="{ 'ok' if ok == 'true' else 'err' }">{title}</h2>
      <p>{message}</p>
      <p>可以关闭此窗口并返回管理后台。</p>
      <button onclick="window.close()">关闭窗口</button>
    </div>
    <script>
      window.opener && window.opener.postMessage({{
        type: 'sjhl-oauth-result',
        ok: {ok},
        resultType: '{html.escape(str((result or {}).get("type") or ""))}',
        profileId: '{profile_id}',
        profileName: '{safe_profile_name}',
        connectionId: '{connection_id}',
        connectionName: '{safe_connection_name}',
        error: '{safe_error}'
      }}, '*');
    </script>
  </body>
</html>"""
