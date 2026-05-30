from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.oauth import OAuthStartRequest
from services.oauth import oauth_callback_html


router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.post("/start")
def start_oauth(body: OAuthStartRequest, container: AppContainer = Depends(get_container)):
    try:
        return container.oauth.start(body.model_dump(exclude_none=True))
    except Exception as error:
        raise_bad_request(error)


@router.get("/callback", response_class=HTMLResponse)
async def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    container: AppContainer = Depends(get_container),
):
    if error:
        return HTMLResponse(oauth_callback_html(error=error_description or error), status_code=400)
    if not code or not state:
        return HTMLResponse(oauth_callback_html(error="OAuth 回调缺少 code 或 state"), status_code=400)
    try:
        result = await container.oauth.callback(state, code)
        return HTMLResponse(oauth_callback_html(result=result))
    except Exception as exc:
        return HTMLResponse(oauth_callback_html(error=str(exc)), status_code=400)


@router.get("/result/{state}")
def oauth_result(state: str, container: AppContainer = Depends(get_container)):
    return {"ok": True, "result": container.oauth.result(state)}
