from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.pan115 import ClouddriveAuthUrlRequest, DownUrlRequest, RefreshOpenTokenRequest
from services.pan115 import DEFAULT_UA


router = APIRouter(prefix="/pan115", tags=["pan115"])


@router.get("/accounts")
def list_accounts(container: AppContainer = Depends(get_container)):
    return {"ok": True, "accounts": container.pan115_accounts.list()}


@router.post("/accounts")
def save_account(body: dict, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "account": container.pan115_accounts.upsert(body)}
    except Exception as error:
        raise_bad_request(error)


@router.delete("/accounts/{account_id}")
def remove_account(account_id: str, container: AppContainer = Depends(get_container)):
    container.pan115_accounts.remove(account_id)
    return {"ok": True}


@router.post("/search")
async def search_files(body: dict, container: AppContainer = Depends(get_container)):
    """搜索115文件"""
    try:
        account = _get_account(container, body.get("accountId", ""))
        token = account.get("accessToken") or ""
        if not token:
            raise ValueError("该账号未配置 Open API Token")
        items = await container.pan115.search_files(token, body.get("keyword", ""), body.get("cid", ""), int(body.get("limit", 100)), int(body.get("offset", 0)))
        return {"ok": True, "items": items}
    except Exception as error:
        raise_bad_request(error)


@router.post("/delete-files")
async def delete_115_files(body: dict, container: AppContainer = Depends(get_container)):
    """删除115文件"""
    try:
        account = _get_account(container, body.get("accountId", ""))
        token = account.get("accessToken") or ""
        if not token:
            raise ValueError("该账号未配置 Open API Token")
        result = await container.pan115.delete_files(token, body.get("fileIds", []), body.get("parentId", "0"))
        return {"ok": True}
    except Exception as error:
        raise_bad_request(error)


@router.post("/create-folder")
async def create_115_folder(body: dict, container: AppContainer = Depends(get_container)):
    """在115新建文件夹"""
    try:
        account = _get_account(container, body.get("accountId", ""))
        token = account.get("accessToken") or ""
        if not token:
            raise ValueError("该账号未配置 Open API Token")
        result = await container.pan115.create_folder(token, body.get("pid", "0"), body.get("name", ""))
        return {"ok": True, "folder": result}
    except Exception as error:
        raise_bad_request(error)


@router.post("/file-info")
async def get_115_file_info(body: dict, container: AppContainer = Depends(get_container)):
    """获取115文件详情"""
    try:
        account = _get_account(container, body.get("accountId", ""))
        token = account.get("accessToken") or ""
        if not token:
            raise ValueError("该账号未配置 Open API Token")
        info = await container.pan115.get_file_info(token, body.get("fileId", ""))
        return {"ok": True, "info": info}
    except Exception as error:
        raise_bad_request(error)


def _get_account(container, account_id: str):
    if not account_id:
        raise ValueError("请提供账号 ID")
    account = container.pan115_accounts.get(account_id)
    if not account:
        raise ValueError("115 账号不存在")
    return account


@router.post("/user-info")
async def get_user_info(body: dict, container: AppContainer = Depends(get_container)):
    """获取115用户信息（优先Open API，降级Cookie查用户名）"""
    try:
        account_id = body.get("accountId", "")
        if account_id:
            account = container.pan115_accounts.get(account_id)
            if not account:
                raise ValueError("115 账号不存在")
        else:
            raise ValueError("请提供账号 ID")
        token = account.get("accessToken") or ""
        if not token:
            raise ValueError("该账号未配置 Open API Token，请先获取 Token")
        try:
            info = await container.pan115.get_user_info(token)
        except Exception:
            # Token 过期，尝试刷新
            refresh = account.get("refreshToken") or ""
            if not refresh:
                raise ValueError("Token 已过期且无 refresh_token，请重新获取 Token")
            try:
                new_tokens = await container.pan115.refresh_open_token(refresh)
                container.pan115_accounts.upsert({"id": account_id, "accessToken": new_tokens["accessToken"], "refreshToken": new_tokens["refreshToken"]})
                info = await container.pan115.get_user_info(new_tokens["accessToken"])
            except Exception:
                raise ValueError("Token 刷新失败，请重新获取 Token")
        return {"ok": True, "info": info}
    except Exception as error:
        raise_bad_request(error)


@router.post("/open/clouddrive/auto-auth")
async def clouddrive_auto_auth(body: dict, container: AppContainer = Depends(get_container)):
    """用已有的 Cookie 自动授权 CloudDrive，获取 access_token + refresh_token"""
    try:
        account_id = body.get("accountId", "")
        if account_id:
            account = container.pan115_accounts.get(account_id)
            if not account:
                raise ValueError("115 账号不存在")
            cookie = account.get("cookie") or ""
        else:
            cookie = body.get("cookie", "")
        if not cookie:
            raise ValueError("请先保存 Cookie")
        tokens = await container.pan115.clouddrive_get_tokens(cookie)
        return {"ok": True, **tokens}
    except Exception as error:
        raise_bad_request(error)


@router.post("/open/clouddrive/auth-url")
async def clouddrive_auth_url(body: ClouddriveAuthUrlRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "authorizationUrl": container.pan115.clouddrive_authorize_url(body.state)}
    except Exception as error:
        raise_bad_request(error)


@router.post("/open/refresh")
async def refresh_open_token(body: RefreshOpenTokenRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, **await container.pan115.refresh_open_token(body.refreshToken)}
    except Exception as error:
        raise_bad_request(error)


class ListDirRequest(BaseModel):
    accountId: str = ""
    cookie: str = ""
    cid: str = "0"


@router.post("/list-dir")
async def list_dir(body: ListDirRequest, container: AppContainer = Depends(get_container)):
    try:
        if body.accountId:
            account = container.pan115_accounts.get(body.accountId)
            if not account:
                raise ValueError("115 账号不存在")
            items = await container.pan115.list_dir_auto(account, body.cid)
        elif body.cookie:
            items = await container.pan115.list_dir_by_cookie(body.cookie, body.cid)
        else:
            raise ValueError("请提供 115 账号 ID 或 Cookie")
        return {"ok": True, "cid": body.cid, "items": items}
    except Exception as error:
        raise_bad_request(error)


@router.post("/down-url")
async def down_url(body: DownUrlRequest, container: AppContainer = Depends(get_container)):
    try:
        user_agent = body.userAgent or DEFAULT_UA
        if body.accessToken or body.refreshToken:
            return {
                "ok": True,
                "file": await container.pan115.down_url(
                    body.accessToken or "",
                    body.pickCode,
                    user_agent,
                    body.refreshToken or "",
                ),
            }
        if body.cookie:
            return {"ok": True, "file": await container.pan115.down_url_by_cookie(body.cookie, body.pickCode, user_agent)}
        raise ValueError("请提供 115 Open token 或 Cookie")
    except Exception as error:
        raise_bad_request(error)
