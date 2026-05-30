from __future__ import annotations

from .common import FlexibleSchema


class OAuthStartRequest(FlexibleSchema):
    profileName: str | None = None
    region: str | None = "cn"
    tenantId: str | None = "common"
    clientId: str
    clientSecret: str | None = ""
    redirectUri: str | None = "http://127.0.0.1:17651/api/oauth/callback"
    scopes: str | None = ""
    driveId: str | None = ""
    siteId: str | None = ""
    siteHostname: str | None = ""
    sitePath: str | None = ""
    libraryName: str | None = ""
    rootPath: str | None = "/media"


class OAuthStartResponse(FlexibleSchema):
    ok: bool = True
    authorizationUrl: str
    state: str
    redirectUri: str
    scopes: str
