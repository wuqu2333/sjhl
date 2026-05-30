from __future__ import annotations

from .common import FlexibleSchema


class LocalUploadRequest(FlexibleSchema):
    profileId: str
    localPath: str
    remoteDir: str | None = ""
    recursive: bool | None = True
    dedupeScope: str | None = "global"
    conflictBehavior: str | None = "fail"


class RemoteUrlUploadRequest(FlexibleSchema):
    profileId: str
    sourceUrl: str | None = None
    headersText: str | None = ""
    fileName: str | None = ""
    remoteDir: str | None = ""
    size: int | str | None = 0
    sha1: str | None = ""
    sha256: str | None = ""
    dedupeScope: str | None = "global"
    conflictBehavior: str | None = "fail"


class Pan115OpenUploadRequest(RemoteUrlUploadRequest):
    accessToken: str | None = None
    refreshToken: str | None = None
    pickCode: str | None = None
    userAgent: str | None = None


class Pan115CookieUploadRequest(RemoteUrlUploadRequest):
    cookie: str | None = None
    pickCode: str | None = None
    userAgent: str | None = None
