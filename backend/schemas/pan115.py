from __future__ import annotations

from .common import FlexibleSchema


class DownUrlRequest(FlexibleSchema):
    cookie: str | None = None
    accessToken: str | None = None
    refreshToken: str | None = None
    pickCode: str
    userAgent: str | None = None


class ClouddriveAuthUrlRequest(FlexibleSchema):
    state: str


class RefreshOpenTokenRequest(FlexibleSchema):
    refreshToken: str
